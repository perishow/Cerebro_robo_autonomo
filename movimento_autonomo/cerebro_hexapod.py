#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exploracao autonoma da rede de bueiros usando o hexapod real."""

import math
import os
import time
import traceback

from hexapod_controller_melhor import (
    HexapodController,
    SYNC_MODE,
    SimulationStoppedManually,
)

try:
    from motor_grafo.grafo_modulo import Grafo
    from motor_grafo.servidor_visualizacao import (
        ServidorVisualizacaoGrafo,
        salvar_snapshot_grafo,
    )
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Pacote motor_grafo ausente. Adicione a pasta completa ao projeto "
        "antes de executar cerebro_hexapod.py."
    ) from exc


JUNCTION_CENTERING_TIME = 18.0
JUNCTION_SCAN_TIME = 1.0
JUNCTION_OPEN_RATIO = 0.70
JUNCTION_MATCH_RADIUS = 0.60

TURN_TOLERANCE_DEG = 3.0
TURN_SETTLE_TIME = 0.50
TURN_TIMEOUT = 30.0
MOTION_STOP_TIMEOUT = 8.0

PIPE_ENTRY_CONFIRM_TIME = 2.0
PIPE_EXIT_CONFIRM_TIME = 2.0
DEBRIS_MAX_DISTANCE = 0.40
DEBRIS_CONFIRM_READINGS = 2

SNAPSHOT_INTERVAL = 0.50


def normalize_angle(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def planar_distance(first, second):
    return math.hypot(first[0] - second[0], first[1] - second[1])


class GraphExplorer:
    """DFS topologico preservado do cerebro abstrato original."""

    def __init__(self, graph, initial_node):
        self.map = graph
        self.current_node = initial_node
        self.path_stack = []
        self.map.atualizar_status_no(initial_node, "visitado")

    def choose_next(self):
        print(f"\n[Cerebro] Pensando... Estou no no: {self.current_node}")
        neighbors = self.map.grafo.get(self.current_node, {})

        for neighbor, edge_data in neighbors.items():
            edge_status = edge_data.get("status", "livre")
            node_status = self.map.nos.get(neighbor, {}).get(
                "status", "não visitado"
            )
            if edge_status == "livre" and node_status == "não visitado":
                print(f"  -> Caminho inedito escolhido: {neighbor}")
                self.path_stack.append(self.current_node)
                self.current_node = neighbor
                self.map.atualizar_status_no(neighbor, "visitado")
                return neighbor

        print("  -> Sem caminhos ineditos; iniciando backtracking.")
        if not self.path_stack:
            print("  -> Exploracao concluida no ponto inicial.")
            return None

        destination = self.path_stack.pop()
        if (
            destination in neighbors
            and neighbors[destination].get("status", "livre") == "livre"
        ):
            self.current_node = destination
            return destination

        for intermediate, edge_data in neighbors.items():
            if edge_data.get("status", "livre") != "livre":
                continue
            if destination in self.map.grafo.get(intermediate, {}):
                if (
                    self.map.grafo[intermediate][destination].get(
                        "status", "livre"
                    )
                    == "livre"
                ):
                    print(
                        f"  -> Backtracking via {intermediate} para {destination}."
                    )
                    self.current_node = intermediate
                    return intermediate

        print(f"  -> Nao existe rota livre de retorno para {destination}.")
        return None


class AutonomousHexapodBrain:
    def __init__(self, robot, graph):
        self.robot = robot
        self.sim = robot.sim
        self.graph = graph
        self.explorer = None
        self.junction_positions = {}
        self.junction_counter = 0
        self.last_snapshot_wall_time = 0.0

    def _step(self):
        self.robot.control_step(manage_legacy_events=False)
        now = time.monotonic()
        if now - self.last_snapshot_wall_time >= SNAPSHOT_INTERVAL:
            salvar_snapshot_grafo(self.graph)
            self.last_snapshot_wall_time = now

    def _run_for(self, duration):
        start = self.sim.getSimulationTime()
        while self.sim.getSimulationTime() - start < duration:
            self._step()

    def _wait_motion_stopped(self):
        start = self.sim.getSimulationTime()
        while not self.robot.motion_stopped():
            if self.sim.getSimulationTime() - start >= MOTION_STOP_TIMEOUT:
                raise RuntimeError("O hexapod nao conseguiu parar no tempo limite.")
            self._step()

    def _average_position(self, samples=20):
        positions = []
        for _ in range(samples):
            position, _ = self.robot.get_pose()
            positions.append(position)
            self._step()
        return [sum(point[axis] for point in positions) / len(positions) for axis in range(3)]

    def _new_junction(self, position):
        self.junction_counter += 1
        node = f"Bueiro_{self.junction_counter}"
        self.graph.adicionar_no(node)
        self.graph.atualizar_status_no(node, "visitado")
        self.junction_positions[node] = list(position)
        print(f"[Mapa] Novo bueiro descoberto: {node}")
        return node

    def _recognize_junction(self, position):
        for node, known_position in self.junction_positions.items():
            if planar_distance(position, known_position) <= JUNCTION_MATCH_RADIUS:
                print(f"[Mapa] Bueiro conhecido reconhecido: {node}")
                return node
        return None

    def _connect(self, origin, destination, origin_angle, destination_angle):
        self.graph.adicionar_conexao(origin, destination, status="livre")
        self.graph.grafo[origin][destination]["angulo"] = normalize_angle(
            origin_angle
        )
        self.graph.grafo[destination][origin]["angulo"] = normalize_angle(
            destination_angle
        )

    def _scan_junction(self, junction):
        print(f"\n[Arquitetura] Mapeando {junction} sem girar o robo...")
        _, orientation = self.robot.get_pose()
        base_yaw = orientation[2]
        votes = {
            "left": {"wall": 0, "total": 0},
            "front": {"wall": 0, "total": 0},
            "right": {"wall": 0, "total": 0},
        }

        start = self.sim.getSimulationTime()
        while self.sim.getSimulationTime() - start < JUNCTION_SCAN_TIME:
            readings = self.robot.read_architecture_walls()
            for direction, reading in readings.items():
                votes[direction]["total"] += 1
                if reading["wall"]:
                    votes[direction]["wall"] += 1
            self._step()

        definitions = {
            "left": ("Esq", normalize_angle(base_yaw + math.pi / 2.0)),
            "front": ("Frente", normalize_angle(base_yaw)),
            "right": ("Dir", normalize_angle(base_yaw - math.pi / 2.0)),
        }
        for direction in ("left", "front", "right"):
            total = max(votes[direction]["total"], 1)
            wall_ratio = votes[direction]["wall"] / total
            open_ratio = 1.0 - wall_ratio
            label, angle = definitions[direction]
            if open_ratio < JUNCTION_OPEN_RATIO:
                print(
                    f"  -> {label}: fechado "
                    f"(parede em {wall_ratio:.0%} das leituras)."
                )
                continue

            pipe_node = f"{junction}_Duto_{label}"
            if pipe_node not in self.graph.grafo:
                self.graph.adicionar_conexao(
                    origem=junction,
                    destino=pipe_node,
                    status="livre",
                )
            self.graph.grafo[junction][pipe_node]["angulo"] = angle
            self.graph.grafo[pipe_node][junction]["angulo"] = normalize_angle(
                angle + math.pi
            )
            print(
                f"  -> {label}: duto aberto confirmado "
                f"({open_ratio:.0%} das leituras sem parede)."
            )

        salvar_snapshot_grafo(self.graph)

    def _align_to(self, target_yaw):
        print(f"[Navegacao] Alinhando para yaw {math.degrees(target_yaw):.1f} deg.")
        self.robot.command_stop()
        self._wait_motion_stopped()
        self.robot.command_heading(target_yaw, turn_in_place=True)

        start = self.sim.getSimulationTime()
        aligned_since = None
        while True:
            now = self.sim.getSimulationTime()
            if now - start >= TURN_TIMEOUT:
                raise RuntimeError("Tempo limite excedido durante o giro no bueiro.")
            if self.robot.heading_aligned(TURN_TOLERANCE_DEG):
                if aligned_since is None:
                    aligned_since = now
                elif now - aligned_since >= TURN_SETTLE_TIME:
                    break
            else:
                aligned_since = None
            self._step()

        self.robot.command_heading(target_yaw, turn_in_place=False)
        self.robot.command_stop()
        self._wait_motion_stopped()
        print("[Navegacao] Alinhamento concluido.")

    def _center_in_junction(self, reverse=False):
        if reverse:
            self.robot.command_reverse()
        else:
            self.robot.command_forward()
        print(
            "[Navegacao] Centralizando no bueiro por "
            f"{JUNCTION_CENTERING_TIME:.1f} s."
        )
        self._run_for(JUNCTION_CENTERING_TIME)
        self.robot.command_stop()
        self._wait_motion_stopped()

    def _wait_for_pipe_entry(self):
        print("[Duto] Avancando ate confirmar a presenca de teto por 2 segundos.")
        detected_since = None
        while True:
            now = self.sim.getSimulationTime()
            if self.robot.ceiling_detected:
                if detected_since is None:
                    detected_since = now
                elif now - detected_since >= PIPE_ENTRY_CONFIRM_TIME:
                    print("[Duto] Entrada confirmada; atravessando o duto.")
                    return
            else:
                detected_since = None
            self._step()

    def _wait_for_pipe_exit_or_debris(self):
        clear_since = None
        debris_readings = 0
        while True:
            now = self.sim.getSimulationTime()
            if (
                self.robot.front_obstacle_detected
                and self.robot.front_obstacle_distance is not None
                and self.robot.front_obstacle_distance <= DEBRIS_MAX_DISTANCE
            ):
                debris_readings += 1
            else:
                debris_readings = 0
            if debris_readings >= DEBRIS_CONFIRM_READINGS:
                return "debris"

            if not self.robot.ceiling_detected:
                if clear_since is None:
                    clear_since = now
                    print("[Duto] Teto perdido; confirmando saida por 2 segundos.")
                elif now - clear_since >= PIPE_EXIT_CONFIRM_TIME:
                    print("[Duto] Saida confirmada; entrando no proximo bueiro.")
                    return "exit"
            else:
                clear_since = None
            self._step()

    def _mark_blocked(self, junction, pipe_node):
        position, _ = self.robot.get_pose()
        try:
            self.graph.atualizar_status_no(pipe_node, "bloqueado")
        except Exception:
            pass
        for origin, destination in ((junction, pipe_node), (pipe_node, junction)):
            edge = self.graph.grafo.get(origin, {}).get(destination)
            if edge is not None:
                edge["status"] = "bloqueado"
                edge["entulho_pos"] = list(position[:2])
        salvar_snapshot_grafo(self.graph)
        print(f"[Bloqueio] {junction} <-> {pipe_node} marcado como bloqueado.")

    def _return_from_debris(self, origin_junction, pipe_node):
        self._mark_blocked(origin_junction, pipe_node)
        print("Entulho detectado, voltando pelo duto")
        self.robot.command_reverse()

        clear_since = None
        while True:
            now = self.sim.getSimulationTime()
            if not self.robot.ceiling_detected:
                if clear_since is None:
                    clear_since = now
                    print("[Retorno] Sem teto; confirmando saida por 2 segundos.")
                elif now - clear_since >= PIPE_EXIT_CONFIRM_TIME:
                    break
            else:
                if clear_since is not None:
                    print("[Retorno] Teto reapareceu; confirmacao reiniciada.")
                clear_since = None
            self._step()

        print("[Retorno] Saida confirmada; centralizando no bueiro anterior.")
        self._center_in_junction(reverse=True)
        if self.explorer.path_stack and self.explorer.path_stack[-1] == origin_junction:
            self.explorer.path_stack.pop()
        self.explorer.current_node = origin_junction
        self.graph.atualizar_status_no(origin_junction, "visitado")

    def _arrive_at_junction(self, pipe_node, travel_yaw):
        self._center_in_junction(reverse=False)
        position = self._average_position()
        junction = self._recognize_junction(position)
        is_new = junction is None
        if is_new:
            junction = self._new_junction(position)

        self._connect(
            pipe_node,
            junction,
            origin_angle=travel_yaw,
            destination_angle=normalize_angle(travel_yaw + math.pi),
        )
        self.explorer.current_node = junction
        self.graph.atualizar_status_no(junction, "visitado")
        if is_new:
            self._scan_junction(junction)
        salvar_snapshot_grafo(self.graph)
        return junction

    def run(self):
        self.robot.command_stop()
        self._wait_motion_stopped()
        initial_position = self._average_position()
        initial_junction = self._new_junction(initial_position)
        self.explorer = GraphExplorer(self.graph, initial_junction)
        self._scan_junction(initial_junction)

        current_junction = initial_junction
        while True:
            next_node = self.explorer.choose_next()
            if next_node is None:
                self.robot.command_stop()
                self._wait_motion_stopped()
                print("\n[Sucesso] Rede acessivel totalmente explorada.")
                return

            edge = self.graph.grafo[current_junction].get(next_node)
            if edge is None or edge.get("status", "livre") != "livre":
                raise RuntimeError(
                    f"Aresta invalida escolhida: {current_junction} -> {next_node}."
                )
            target_yaw = edge["angulo"]
            self._align_to(target_yaw)
            self.robot.command_forward()
            self._wait_for_pipe_entry()
            outcome = self._wait_for_pipe_exit_or_debris()

            if outcome == "debris":
                self._return_from_debris(current_junction, next_node)
                current_junction = self.explorer.current_node
                continue

            current_junction = self._arrive_at_junction(next_node, target_yaw)


def main():
    robot = HexapodController()
    sim = robot.sim
    graph = Grafo()
    visualizer = None

    if os.environ.get("VISUALIZADOR_SEPARADO") != "1":
        visualizer = ServidorVisualizacaoGrafo(graph)
        visualizer.iniciar()

    try:
        if SYNC_MODE:
            sim.setStepping(True)
        robot.ensure_simulation_stopped()
        robot.init()
        sim.startSimulation()
        robot.reset_to_initial_pose()
        robot.settle_and_calibrate()

        print("Cerebro do hexapod iniciado.")
        AutonomousHexapodBrain(robot, graph).run()
    except SimulationStoppedManually as exc:
        print(f"{exc} Cerebro encerrado com seguranca.")
    except KeyboardInterrupt:
        print("\n[Sistema] Interrompido pelo usuario.")
    except Exception:
        print("\n[ERRO CRITICO] Falha no cerebro do hexapod:")
        traceback.print_exc()
    finally:
        try:
            robot.ensure_simulation_stopped()
        except Exception:
            pass
        salvar_snapshot_grafo(graph)
        if visualizer:
            visualizer.parar()
        print("\nMapa final:")
        graph.mostrar_grafo()


if __name__ == "__main__":
    main()
