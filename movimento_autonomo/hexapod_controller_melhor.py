#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Marcha reta de um hexapod para piso plano e duto cilindrico.

Sensores esperados na cena do CoppeliaSim:

* bottomSensor: no centro do corpo, apontado verticalmente para baixo;
* leftDepthSensor: na lateral esquerda, apontado verticalmente para baixo;
* rightDepthSensor: na lateral direita, apontado verticalmente para baixo;
* frontalSensor: na frente do corpo, apontado para a area a inspecionar;
* upSensor: no corpo, apontado para cima para detectar teto;
* superFrontalSensor: verifica a arquitetura a frente no centro do bueiro;
* superLeftSensor: verifica a arquitetura a esquerda no centro do bueiro;
* superRightSensor: verifica a arquitetura a direita no centro do bueiro;
* GyroSensor: preso ao corpo, com os eixos alinhados aos eixos do robo.

Os sensores laterais medem continuamente a diferenca de altura entre o piso sob
cada lado e o piso sob o centro do corpo. Essa diferenca desloca verticalmente
as patas de cada lado, permitindo que a postura acompanhe gradualmente a curva
do duto. A orientacao do GyroSensor nivela o plano das seis patas e amortece as
oscilacoes do corpo.
"""

import math
import time

from coppeliasim_zmqremoteapi_client import RemoteAPIClient


# Conexao e simulacao
COPPELIA_HOST = "localhost"
COPPELIA_PORT = 23000
SYNC_MODE = True

# Nomes dos sensores usados
BOTTOM_SENSOR_NAME = "bottomSensor"
LEFT_DEPTH_SENSOR_NAME = "leftDepthSensor"
RIGHT_DEPTH_SENSOR_NAME = "rightDepthSensor"
FRONTAL_SENSOR_NAME = "frontalSensor"
UP_SENSOR_NAME = "upSensor"
SUPER_FRONTAL_SENSOR_NAME = "superFrontalSensor"
SUPER_LEFT_SENSOR_NAME = "superLeftSensor"
SUPER_RIGHT_SENSOR_NAME = "superRightSensor"
GYRO_SENSOR_NAME = "GyroSensor"

CEILING_CONFIRM_TIME = 2.0
CEILING_LOST_CONFIRM_TIME = 2.0
DIRECTION_CHANGE_RATE = 1.5

# Marcha: wave gait mantem cinco patas apoiadas e privilegia estabilidade.
WALK_VEL = 0.50
WALK_AMPLITUDE = 0.08
WALK_STEP_HEIGHT = 0.09
SWING_FRACTION = 0.15       # <= 1/6: no maximo uma pata no ar

# O robo nasce com a barriga muito perto do piso. Eleva o corpo suavemente e
# mantem essa altura antes de criar as referencias do sensor inferior e do gyro.
STARTUP_BODY_RAISE = 0.03
STARTUP_RAISE_TIME = 2.0
STARTUP_SETTLE_TIME = 1.0

# Adaptacao continua das patas ao perfil lateral do piso. O deslocamento e
# calculado pela altura mundial dos pontos detectados, sem confundir inclinacao
# do sensor com mudanca no terreno.
DEPTH_SENSOR_FILTER = 0.15
TERRAIN_ADAPTATION_GAIN = 1.0
TERRAIN_DEADBAND = 0.005
MAX_TERRAIN_OFFSET = 0.040
TERRAIN_FREEZE_TILT_DEG = 3.0
TERRAIN_RELEASE_RATE = 3.0
TERRAIN_ENGAGE_RATE = 1.0

# Redistribuicao de tracao dentro do duto. As duas patas mais laterais sao
# encurtadas e as outras quatro sao alongadas proporcionalmente, evitando que
# o corpo fique sustentado somente nos dois pontos mais altos do cilindro.
PIPE_ENTER_HEIGHT = 0.020
PIPE_EXIT_HEIGHT = 0.010
PIPE_SYMMETRY_TOLERANCE = 0.020
PIPE_DETECTION_TIME = 0.50
PIPE_RELIEF_GAIN = 10
MAX_LATERAL_RELIEF = 0.020
MIN_PIPE_LATERAL_RELIEF = 0.010
PIPE_SUPPORT_EXTENSION_RATIO = 0.50
MAX_PIPE_SUPPORT_EXTENSION = 0.010
# Evita que a adaptacao lateral encurte novamente as quatro patas que o modo
# duto esta tentando apoiar. Zero entrega o controle vertical ao modo duto.
PIPE_TERRAIN_INFLUENCE = 0.0
PIPE_RELIEF_RATE = 0.030
PIPE_RELIEF_SIGN = 1.0

# Nesta montagem, a frente correta e a aresta superior do corpo: eixo local +Y.
# X fica sendo apenas o eixo lateral (esquerda/direita).
FORWARD_Y_SIGN = 1.0

# Controle proporcional de altura
TARGET_GROUND_DISTANCE = 0.04   # None calibra automaticamente no piso inicial
HEIGHT_KP = 0.65
MAX_HEIGHT_CORRECTION = 0.035
SENSOR_FILTER = 0.20

# Controle PD do giroscopio. Resposta mais energica para recuperar rapidamente
# a postura, mantendo o termo D para amortecer a correcao.
GYRO_KP = 1.20
GYRO_KD = 0.05
GYRO_RATE_FILTER = 0.35
GYRO_DEADBAND_DEG = 1.5
MAX_GYRO_CONTROL_DEG = 15.0
MAX_LEG_BALANCE_CORRECTION = 0.035

# Controle de rumo: mantem o yaw registrado ao final da calibracao. O comando
# e misturado a passada como uma componente de rotacao em torno do corpo.
HEADING_KP = 1.50
HEADING_KD = 0.08
HEADING_DEADBAND_DEG = 2.0
MAX_HEADING_STEER = 0.55

# Inverta somente se a montagem responder no sentido contrario.
HEIGHT_CORRECTION_SIGN = 1.0
GYRO_CORRECTION_SIGN = -1.0
HEADING_CORRECTION_SIGN = 1.0


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def angle_error(target, current):
    return (target - current + math.pi) % (2.0 * math.pi) - math.pi


def apply_deadband(value, threshold):
    """Remove ruido perto de zero sem criar salto ao cruzar o limiar."""
    if abs(value) <= threshold:
        return 0.0
    return math.copysign(abs(value) - threshold, value)


def move_toward(current, target, max_delta):
    """Aproxima um valor do alvo sem ultrapassar a variacao permitida."""
    return current + clamp(target - current, -max_delta, max_delta)


class SimulationStoppedManually(RuntimeError):
    """Interrompe o controlador sem executar novos comandos de movimento."""

    def __init__(self, message, state=None, simulation_time=None):
        super().__init__(message)
        self.state = state
        self.simulation_time = simulation_time


class HexapodController:
    def __init__(self):
        self.client = RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PORT)
        self.sim = self.client.require("sim")
        self.simIK = self.client.require("simIK")

        self.base = None
        self.leg_base = None
        self.leg_tips = []
        self.leg_targets = []
        self.initial_feet = []
        self.initial_leg_base_pos = None
        self.initial_leg_base_euler = None
        self.initial_model_configuration = None

        self.bottom_sensor = None
        self.left_depth_sensor = None
        self.right_depth_sensor = None
        self.frontal_sensor = None
        self.up_sensor = None
        self.super_frontal_sensor = None
        self.super_left_sensor = None
        self.super_right_sensor = None
        self.gyro_sensor = None
        self.model_root = None

        self.ik_env = None
        self.ik_group = None
        self.leg_movement_index = [1, 4, 2, 6, 3, 5]
        self.step_progression = 0.0
        self.movement_strength = 0.0

        self.target_ground_distance = TARGET_GROUND_DISTANCE
        self.filtered_ground_distance = None
        self.bottom_surface_reference = None
        self.left_surface_reference = None
        self.right_surface_reference = None
        self.filtered_bottom_surface = None
        self.filtered_left_surface = None
        self.filtered_right_surface = None
        self.left_terrain_offset = 0.0
        self.right_terrain_offset = 0.0
        self.terrain_blend = 1.0
        self.left_profile_height = 0.0
        self.right_profile_height = 0.0
        self.pipe_mode = False
        self.pipe_enter_time = 0.0
        self.pipe_exit_time = 0.0
        self.lateral_relief = 0.0
        self.lateral_relief_legs = set()
        self.front_obstacle_detected = False
        self.front_obstacle_distance = None
        self.debris_detected_event = False
        self.ceiling_detected = False
        self.ceiling_detected_since = None
        self.ceiling_confirmed = False
        self.ceiling_lost_since = None
        self.travel_command = 1.0
        self.target_travel_command = 1.0
        self.returning_from_debris = False
        self.return_from_debris_completed = False
        self.gyro_reference = [0.0, 0.0, 0.0]
        self.gyro_last_orientation = [0.0, 0.0, 0.0]
        self.gyro_rate = [0.0, 0.0, 0.0]
        self.heading_steer = 0.0
        self.navigation_turning = False
        self.leg_balance_correction = [0.0] * 6
        self.left_x_sign = 1.0

    def init(self):
        sim = self.sim
        sim_ik = self.simIK

        self.base = sim.getObject("/base")
        self.leg_base = sim.getObject("/legBase")
        self.leg_tips = [sim.getObject("/footTip" + str(i)) for i in range(6)]
        self.leg_targets = [sim.getObject("/footTarget" + str(i)) for i in range(6)]
        # Os targets sao referencias cinematicas estaveis da cena. Os tips
        # acompanham as juntas fisicas e podem estar tortos depois de uma queda.
        self.initial_feet = [
            sim.getObjectPosition(self.leg_targets[i], self.leg_base)
            for i in range(6)
        ]
        self.initial_leg_base_pos = sim.getObjectPosition(self.leg_base, self.base)
        self.initial_leg_base_euler = sim.getObjectOrientation(self.leg_base, self.base)

        self.model_root = sim.getObjectParent(self.base)
        self.initial_model_configuration = sim.getConfigurationTree(self.model_root)
        self.ik_env = sim_ik.createEnvironment()
        self.ik_group = sim_ik.createGroup(self.ik_env)
        for i in range(6):
            sim_ik.addElementFromScene(
                self.ik_env,
                self.ik_group,
                self.model_root,
                self.leg_tips[i],
                self.leg_targets[i],
                sim_ik.constraint_position,
            )

        self.bottom_sensor = self._required_sensor(BOTTOM_SENSOR_NAME)
        self.left_depth_sensor = self._required_sensor(LEFT_DEPTH_SENSOR_NAME)
        self.right_depth_sensor = self._required_sensor(RIGHT_DEPTH_SENSOR_NAME)
        self.frontal_sensor = self._required_sensor(FRONTAL_SENSOR_NAME)
        self.up_sensor = self._required_sensor(UP_SENSOR_NAME)
        self.super_frontal_sensor = self._required_sensor(SUPER_FRONTAL_SENSOR_NAME)
        self.super_left_sensor = self._required_sensor(SUPER_LEFT_SENSOR_NAME)
        self.super_right_sensor = self._required_sensor(SUPER_RIGHT_SENSOR_NAME)
        self.gyro_sensor = self._required_sensor(GYRO_SENSOR_NAME)
        left_x = sim.getObjectPosition(self.left_depth_sensor, self.leg_base)[0]
        right_x = sim.getObjectPosition(self.right_depth_sensor, self.leg_base)[0]
        self.left_x_sign = 1.0 if left_x > right_x else -1.0
        center_x = sum(foot[0] for foot in self.initial_feet) / 6.0
        left_legs = [
            leg
            for leg, foot in enumerate(self.initial_feet)
            if (foot[0] - center_x) * self.left_x_sign > 0.0
        ]
        right_legs = [
            leg
            for leg, foot in enumerate(self.initial_feet)
            if (foot[0] - center_x) * self.left_x_sign < 0.0
        ]
        if not left_legs or not right_legs:
            raise RuntimeError("Nao foi possivel separar as patas por lateral.")
        self.lateral_relief_legs = {
            max(left_legs, key=lambda leg: abs(self.initial_feet[leg][0] - center_x)),
            max(right_legs, key=lambda leg: abs(self.initial_feet[leg][0] - center_x)),
        }
        print("[init] IK, sensores de profundidade/frontal e GyroSensor configurados.")
        print(
            "[init] Patas extremas para redistribuicao no duto: %s."
            % sorted(self.lateral_relief_legs)
        )

    def reset_to_initial_pose(self):
        """Restaura o modelo e resolve as patas para os alvos iniciais da cena."""
        self._ensure_simulation_running()
        self.sim.setConfigurationTree(self.initial_model_configuration)

        self.step_progression = 0.0
        self.movement_strength = 0.0
        self.heading_steer = 0.0
        self.leg_balance_correction = [0.0] * 6
        self.left_terrain_offset = 0.0
        self.right_terrain_offset = 0.0
        self.terrain_blend = 1.0
        self.left_profile_height = 0.0
        self.right_profile_height = 0.0
        self.pipe_mode = False
        self.pipe_enter_time = 0.0
        self.pipe_exit_time = 0.0
        self.lateral_relief = 0.0
        self.front_obstacle_detected = False
        self.front_obstacle_distance = None
        self.debris_detected_event = False
        self.ceiling_detected = False
        self.ceiling_detected_since = None
        self.ceiling_confirmed = False
        self.ceiling_lost_since = None
        self.travel_command = 1.0
        self.target_travel_command = 1.0
        self.returning_from_debris = False
        self.return_from_debris_completed = False

        for leg, neutral_position in enumerate(self.initial_feet):
            self.sim.setObjectPosition(
                self.leg_targets[leg], neutral_position, self.leg_base
            )

        self.simIK.handleGroup(
            self.ik_env,
            self.ik_group,
            {"syncWorlds": True, "allowError": True},
        )
        print("[init] Configuracao inicial do hexapod restaurada.")

    def ensure_simulation_stopped(self, timeout=10.0):
        """Espera o CoppeliaSim terminar e restaurar a cena anterior."""
        if self.sim.getSimulationState() == self.sim.simulation_stopped:
            return

        self.sim.stopSimulation()
        deadline = time.monotonic() + timeout
        while self.sim.getSimulationState() != self.sim.simulation_stopped:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "CoppeliaSim nao concluiu a parada da simulacao anterior."
                )
            time.sleep(0.05)

    def _ensure_simulation_running(self):
        """Aborta antes de escrever na cena se houve parada ou pausa externa."""
        state = self.sim.getSimulationState()
        paused_states = {
            getattr(self.sim, "simulation_paused", -1),
            getattr(self.sim, "simulation_advancing_lastbeforepause", -4),
        }
        stopped_states = {
            self.sim.simulation_stopped,
            getattr(self.sim, "simulation_advancing_abouttostop", -2),
            getattr(self.sim, "simulation_advancing_lastbeforestop", -3),
        }
        if state in paused_states or state in stopped_states:
            try:
                simulation_time = self.sim.getSimulationTime()
            except Exception:
                simulation_time = None
            if state in paused_states:
                reason = (
                    "CoppeliaSim pausou externamente ou por uma configuracao "
                    "da cena"
                )
            else:
                reason = "CoppeliaSim recebeu uma solicitacao externa de Stop"
            timing = (
                f" em t={simulation_time:.2f} s"
                if simulation_time is not None
                else ""
            )
            raise SimulationStoppedManually(
                f"{reason}{timing} (estado={state}).",
                state=state,
                simulation_time=simulation_time,
            )

    def _required_sensor(self, name):
        try:
            return self.sim.getObject("/" + name)
        except Exception as exc:
            raise RuntimeError("Sensor obrigatorio nao encontrado: /" + name) from exc

    def _belongs_to_robot(self, handle):
        current = handle
        for _ in range(15):
            if current is None or current < 0:
                return False
            if current == self.model_root:
                return True
            current = self.sim.getObjectParent(current)
        return False

    def _local_to_world(self, handle, local_point):
        """Transforma um ponto local do sensor em coordenadas mundiais."""
        matrix = self.sim.getObjectMatrix(handle, -1)
        x, y, z = local_point
        return [
            matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3],
            matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7],
            matrix[8] * x + matrix[9] * y + matrix[10] * z + matrix[11],
        ]

    def _sensor_measurement(self, sensor):
        """Retorna (distancia, altura mundial do ponto) ou None."""
        result = self.sim.checkProximitySensor(sensor, self.sim.handle_all)
        detected = result[0] if result else False
        distance = result[1] if len(result) > 1 else None
        detected_point = result[2] if len(result) > 2 else None
        object_handle = result[3] if len(result) > 3 else None
        if not detected or distance is None or self._belongs_to_robot(object_handle):
            return None
        if detected_point is None or len(detected_point) < 3:
            return float(distance), None
        world_point = self._local_to_world(sensor, detected_point)
        return float(distance), float(world_point[2])

    def _sensor_distance(self, sensor):
        measurement = self._sensor_measurement(sensor)
        return None if measurement is None else measurement[0]

    def _update_front_sensor_test(self, manage_legacy_return=True):
        """Atualiza o entulho frontal e opcionalmente inicia o retorno legado."""
        measurement = self._sensor_measurement(self.frontal_sensor)
        detected = measurement is not None
        self.front_obstacle_distance = None if measurement is None else measurement[0]
        self.debris_detected_event = detected and not self.front_obstacle_detected
        if (
            manage_legacy_return
            and self.debris_detected_event
            and not self.returning_from_debris
            and not self.return_from_debris_completed
        ):
            print("Entulho detectado, voltando pelo duto")
            self.returning_from_debris = True
            self.command_reverse()
        self.front_obstacle_detected = detected

    def read_architecture_walls(self):
        """Retorna deteccao de parede e distancia em esquerda/frente/direita."""
        sensors = {
            "left": self.super_left_sensor,
            "front": self.super_frontal_sensor,
            "right": self.super_right_sensor,
        }
        result = {}
        for direction, sensor in sensors.items():
            measurement = self._sensor_measurement(sensor)
            result[direction] = {
                "wall": measurement is not None,
                "distance": None if measurement is None else measurement[0],
            }
        return result

    def get_pose(self):
        """Retorna posicao e orientacao mundiais da base fisica."""
        return (
            list(self.sim.getObjectPosition(self.base, -1)),
            list(self.sim.getObjectOrientation(self.base, -1)),
        )

    def command_forward(self):
        self.navigation_turning = False
        self.target_travel_command = 1.0

    def command_reverse(self):
        self.navigation_turning = False
        self.target_travel_command = -1.0

    def command_stop(self):
        self.target_travel_command = 0.0

    def command_heading(self, yaw, turn_in_place=True):
        """Define o yaw mundial desejado e habilita giro no proprio eixo."""
        self.gyro_reference[2] = angle_error(yaw, 0.0)
        self.navigation_turning = bool(turn_in_place)
        if turn_in_place:
            self.target_travel_command = 0.0

    def heading_error(self):
        orientation = self.sim.getObjectOrientation(self.gyro_sensor, -1)
        return angle_error(self.gyro_reference[2], orientation[2])

    def heading_aligned(self, tolerance_deg=3.0):
        return abs(self.heading_error()) <= math.radians(tolerance_deg)

    def motion_stopped(self, tolerance=0.03):
        return abs(self.travel_command) <= tolerance

    def _update_up_sensor_test(self):
        """Informa a deteccao inicial e confirma um teto persistente."""
        detected = self._sensor_measurement(self.up_sensor) is not None
        now = self.sim.getSimulationTime()
        if detected and not self.ceiling_detected:
            print("teto detectado, provavelmente estamos em um duto")
            self.ceiling_detected_since = now
            self.ceiling_confirmed = False
        elif (
            detected
            and not self.ceiling_confirmed
            and self.ceiling_detected_since is not None
            and now - self.ceiling_detected_since >= CEILING_CONFIRM_TIME
        ):
            print("com certeza estamos em um duto")
            self.ceiling_confirmed = True
        elif not detected:
            self.ceiling_detected_since = None
            self.ceiling_confirmed = False
        self.ceiling_detected = detected

    def _update_return_from_debris(self):
        """Confirma a ausencia de teto antes de encerrar o retorno."""
        if not self.returning_from_debris:
            self.ceiling_lost_since = None
            return

        now = self.sim.getSimulationTime()
        if self.ceiling_detected:
            if self.ceiling_lost_since is not None:
                print("Teto detectado novamente; contagem de saida cancelada")
            self.ceiling_lost_since = None
            return

        if self.ceiling_lost_since is None:
            self.ceiling_lost_since = now
            print(
                "Teto nao detectado; aguardando %.1f segundos para confirmar a saida"
                % CEILING_LOST_CONFIRM_TIME
            )
            return

        if now - self.ceiling_lost_since >= CEILING_LOST_CONFIRM_TIME:
            print("Saida do duto confirmada; parando o retorno")
            self.returning_from_debris = False
            self.return_from_debris_completed = True
            self.target_travel_command = 0.0
            self.ceiling_lost_since = None

    def settle_and_calibrate(self):
        """Eleva o corpo, espera estabilizar e somente entao calibra sensores."""
        dt = max(self.sim.getSimulationTimeStep(), 1e-3)
        steps = max(1, int(STARTUP_RAISE_TIME / dt))
        for step in range(1, steps + 1):
            self._ensure_simulation_running()
            progress = step / steps
            # Smoothstep evita tranco no inicio e no fim da elevacao.
            smooth = progress * progress * (3.0 - 2.0 * progress)
            pos = list(self.initial_leg_base_pos)
            pos[2] += STARTUP_BODY_RAISE * smooth
            self.sim.setObjectPosition(self.leg_base, pos, self.base)
            self.simIK.handleGroup(
                self.ik_env,
                self.ik_group,
                {"syncWorlds": True, "allowError": True},
            )
            self._advance_sim()

        settle_steps = max(1, int(STARTUP_SETTLE_TIME / dt))
        for _ in range(settle_steps):
            self._ensure_simulation_running()
            self.simIK.handleGroup(
                self.ik_env,
                self.ik_group,
                {"syncWorlds": True, "allowError": True},
            )
            self._advance_sim()

        sensor_samples = {
            "bottom": {"distance": [], "surface": []},
            "left": {"distance": [], "surface": []},
            "right": {"distance": [], "surface": []},
        }
        for _ in range(20):
            self._ensure_simulation_running()
            measurements = {
                "bottom": self._sensor_measurement(self.bottom_sensor),
                "left": self._sensor_measurement(self.left_depth_sensor),
                "right": self._sensor_measurement(self.right_depth_sensor),
            }
            for name, measurement in measurements.items():
                if measurement is not None:
                    distance, surface_height = measurement
                    sensor_samples[name]["distance"].append(distance)
                    if surface_height is not None:
                        sensor_samples[name]["surface"].append(surface_height)
            self._advance_sim()

        sensor_names = {
            "bottom": BOTTOM_SENSOR_NAME,
            "left": LEFT_DEPTH_SENSOR_NAME,
            "right": RIGHT_DEPTH_SENSOR_NAME,
        }
        for name, samples in sensor_samples.items():
            if not samples["distance"] or not samples["surface"]:
                raise RuntimeError(
                    "%s nao forneceu uma leitura valida do piso na calibracao."
                    % sensor_names[name]
                )

        bottom_distance_reference = sum(
            sensor_samples["bottom"]["distance"]
        ) / len(sensor_samples["bottom"]["distance"])
        self.bottom_surface_reference = sum(
            sensor_samples["bottom"]["surface"]
        ) / len(sensor_samples["bottom"]["surface"])
        self.left_surface_reference = sum(
            sensor_samples["left"]["surface"]
        ) / len(sensor_samples["left"]["surface"])
        self.right_surface_reference = sum(
            sensor_samples["right"]["surface"]
        ) / len(sensor_samples["right"]["surface"])
        if self.target_ground_distance is None:
            self.target_ground_distance = bottom_distance_reference

        self.filtered_ground_distance = bottom_distance_reference
        self.filtered_bottom_surface = self.bottom_surface_reference
        self.filtered_left_surface = self.left_surface_reference
        self.filtered_right_surface = self.right_surface_reference

        # Captura inclinacao e rumo imediatamente antes da caminhada. Isso evita
        # que o tempo gasto amostrando os sensores gere um pico falso de derivada.
        gyro_orientation = self.sim.getObjectOrientation(self.gyro_sensor, -1)
        self.gyro_reference = list(gyro_orientation[:3])
        self.gyro_last_orientation = list(gyro_orientation[:3])
        self.gyro_rate = [0.0, 0.0, 0.0]
        self.heading_steer = 0.0
        self.navigation_turning = False
        print(
            "[calibracao] Corpo elevado %.3f m; distancia central: %.3f m; "
            "perfil lateral E/D: %.3f/%.3f m; inclinacao X/Y: %.1f/%.1f deg; "
            "rumo: %.1f deg."
            % (
                STARTUP_BODY_RAISE,
                bottom_distance_reference,
                self.left_surface_reference - self.bottom_surface_reference,
                self.right_surface_reference - self.bottom_surface_reference,
                math.degrees(self.gyro_reference[0]),
                math.degrees(self.gyro_reference[1]),
                math.degrees(self.gyro_reference[2]),
            )
        )

    def _update_terrain_profile(self):
        """Atualiza continuamente a altura relativa do piso em cada lateral."""
        dt = max(self.sim.getSimulationTimeStep(), 1e-3)
        orientation = self.sim.getObjectOrientation(self.gyro_sensor, -1)
        tilt_error = max(
            abs(angle_error(self.gyro_reference[axis], orientation[axis]))
            for axis in range(2)
        )
        if tilt_error > math.radians(TERRAIN_FREEZE_TILT_DEG):
            # Durante uma inclinacao relevante, o giroscopio ganha prioridade.
            # O perfil deixa de aprender a oscilacao e sua influencia e retirada
            # gradualmente, sem provocar um salto nas patas.
            self.terrain_blend = max(
                0.0, self.terrain_blend - TERRAIN_RELEASE_RATE * dt
            )
            # O perfil e congelado, mas o teto confirmado ainda mantem a
            # redistribuicao de tracao ativa enquanto o corpo se recupera.
            self._update_pipe_relief(dt, profile_is_valid=False)
            return

        self.terrain_blend = min(
            1.0, self.terrain_blend + TERRAIN_ENGAGE_RATE * dt
        )

        measurements = {
            "bottom": self._sensor_measurement(self.bottom_sensor),
            "left": self._sensor_measurement(self.left_depth_sensor),
            "right": self._sensor_measurement(self.right_depth_sensor),
        }
        surfaces = {
            name: None if value is None else value[1]
            for name, value in measurements.items()
        }

        if surfaces["bottom"] is not None:
            self.filtered_bottom_surface += DEPTH_SENSOR_FILTER * (
                surfaces["bottom"] - self.filtered_bottom_surface
            )
        if surfaces["left"] is not None:
            self.filtered_left_surface += DEPTH_SENSOR_FILTER * (
                surfaces["left"] - self.filtered_left_surface
            )
        if surfaces["right"] is not None:
            self.filtered_right_surface += DEPTH_SENSOR_FILTER * (
                surfaces["right"] - self.filtered_right_surface
            )

        initial_left_profile = (
            self.left_surface_reference - self.bottom_surface_reference
        )
        initial_right_profile = (
            self.right_surface_reference - self.bottom_surface_reference
        )
        current_left_profile = (
            self.filtered_left_surface - self.filtered_bottom_surface
        )
        current_right_profile = (
            self.filtered_right_surface - self.filtered_bottom_surface
        )
        self.left_profile_height = current_left_profile - initial_left_profile
        self.right_profile_height = current_right_profile - initial_right_profile

        self.left_terrain_offset = clamp(
            TERRAIN_ADAPTATION_GAIN
            * apply_deadband(
                self.left_profile_height,
                TERRAIN_DEADBAND,
            ),
            -MAX_TERRAIN_OFFSET,
            MAX_TERRAIN_OFFSET,
        )
        self.right_terrain_offset = clamp(
            TERRAIN_ADAPTATION_GAIN
            * apply_deadband(
                self.right_profile_height,
                TERRAIN_DEADBAND,
            ),
            -MAX_TERRAIN_OFFSET,
            MAX_TERRAIN_OFFSET,
        )
        profile_is_valid = all(value is not None for value in surfaces.values())
        self._update_pipe_relief(dt, profile_is_valid)

    def _update_pipe_relief(self, dt, profile_is_valid):
        """Detecta o duto e redistribui o apoio entre as seis patas."""
        if self.ceiling_confirmed and not self.pipe_mode:
            self.pipe_mode = True
            self.pipe_enter_time = 0.0
            self.pipe_exit_time = 0.0
            print(
                "[duto] Teto confirmado; ativando redistribuicao de tracao."
            )

        if profile_is_valid:
            symmetric = (
                abs(self.left_profile_height - self.right_profile_height)
                <= PIPE_SYMMETRY_TOLERANCE
            )
            enter_condition = (
                self.left_profile_height >= PIPE_ENTER_HEIGHT
                and self.right_profile_height >= PIPE_ENTER_HEIGHT
                and symmetric
            )
            exit_condition = (
                self.left_profile_height <= PIPE_EXIT_HEIGHT
                and self.right_profile_height <= PIPE_EXIT_HEIGHT
            )

            if not self.pipe_mode:
                self.pipe_enter_time = (
                    self.pipe_enter_time + dt if enter_condition else 0.0
                )
                if self.pipe_enter_time >= PIPE_DETECTION_TIME:
                    self.pipe_mode = True
                    self.pipe_enter_time = 0.0
                    self.pipe_exit_time = 0.0
                    print(
                        "[duto] Perfil cilindrico confirmado; redistribuindo tracao."
                    )
            else:
                self.pipe_exit_time = (
                    self.pipe_exit_time + dt
                    if exit_condition and not self.ceiling_confirmed
                    else 0.0
                )
                if self.pipe_exit_time >= PIPE_DETECTION_TIME:
                    self.pipe_mode = False
                    self.pipe_exit_time = 0.0
                    self.pipe_enter_time = 0.0
                    print(
                        "[duto] Saida confirmada; retornando ao apoio normal."
                    )

        target_relief = 0.0
        if self.pipe_mode:
            curvature = min(self.left_profile_height, self.right_profile_height)
            target_relief = clamp(
                max(
                    MIN_PIPE_LATERAL_RELIEF,
                    PIPE_RELIEF_GAIN
                    * max(0.0, curvature - PIPE_ENTER_HEIGHT),
                ),
                0.0,
                MAX_LATERAL_RELIEF,
            )
        self.lateral_relief = move_toward(
            self.lateral_relief,
            target_relief,
            PIPE_RELIEF_RATE * dt,
        )

    def _update_posture(self):
        """Corrige a altura media e atualiza a compensacao de cada pata."""
        self._ensure_simulation_running()
        ground_distance = self._sensor_distance(self.bottom_sensor)
        if ground_distance is not None:
            self.filtered_ground_distance += SENSOR_FILTER * (
                ground_distance - self.filtered_ground_distance
            )

        height_error = self.target_ground_distance - self.filtered_ground_distance
        height_correction = clamp(
            HEIGHT_CORRECTION_SIGN * HEIGHT_KP * height_error,
            -MAX_HEIGHT_CORRECTION,
            MAX_HEIGHT_CORRECTION,
        )

        pos = list(self.initial_leg_base_pos)
        pos[2] += STARTUP_BODY_RAISE + height_correction
        self.sim.setObjectPosition(self.leg_base, pos, self.base)
        self._update_gyro_compensation()

    def _update_gyro_compensation(self):
        """Transforma inclinacao e velocidade angular em extensao das patas.

        O plano corretivo usa z = angulo_x*y - angulo_y*x. Dessa forma, patas
        em lados opostos recebem correcoes opostas sem alterar a altura media.
        """
        dt = max(self.sim.getSimulationTimeStep(), 1e-3)
        orientation = self.sim.getObjectOrientation(self.gyro_sensor, -1)

        raw_rate = [
            angle_error(orientation[axis], self.gyro_last_orientation[axis]) / dt
            for axis in range(3)
        ]
        for axis in range(3):
            self.gyro_rate[axis] += GYRO_RATE_FILTER * (
                raw_rate[axis] - self.gyro_rate[axis]
            )
        self.gyro_last_orientation = list(orientation[:3])

        deadband = math.radians(GYRO_DEADBAND_DEG)
        max_control = math.radians(MAX_GYRO_CONTROL_DEG)
        control = []
        for axis in range(2):
            error = angle_error(self.gyro_reference[axis], orientation[axis])

            # A marcha produz pequenas inclinacoes periodicas naturais. Dentro
            # da zona morta, zera tambem o termo derivativo para o controlador
            # nao lutar contra esse movimento. Fora dela, desconta o limiar
            # para que o comando cresca suavemente a partir de zero.
            if abs(error) <= deadband:
                command = 0.0
            else:
                effective_error = math.copysign(abs(error) - deadband, error)
                command = (
                    GYRO_KP * effective_error
                    - GYRO_KD * self.gyro_rate[axis]
                )
            control.append(clamp(command, -max_control, max_control))

        center_x = sum(foot[0] for foot in self.initial_feet) / 6.0
        center_y = sum(foot[1] for foot in self.initial_feet) / 6.0
        for leg, foot in enumerate(self.initial_feet):
            x = foot[0] - center_x
            y = foot[1] - center_y
            correction = GYRO_CORRECTION_SIGN * (control[0] * y - control[1] * x)
            self.leg_balance_correction[leg] = clamp(
                correction,
                -MAX_LEG_BALANCE_CORRECTION,
                MAX_LEG_BALANCE_CORRECTION,
            )

        heading_error = angle_error(self.gyro_reference[2], orientation[2])
        effective_heading_error = apply_deadband(
            heading_error, math.radians(HEADING_DEADBAND_DEG)
        )
        if effective_heading_error == 0.0:
            self.heading_steer = 0.0
        else:
            self.heading_steer = clamp(
                HEADING_KP * effective_heading_error
                - HEADING_KD * self.gyro_rate[2],
                -MAX_HEADING_STEER,
                MAX_HEADING_STEER,
            )

    def _terrain_offset_for_leg(self, leg):
        """Retorna o perfil medido pelo sensor do mesmo lado da pata."""
        center_x = sum(foot[0] for foot in self.initial_feet) / 6.0
        is_left = (
            (self.initial_feet[leg][0] - center_x) * self.left_x_sign > 0.0
        )
        offset = self.left_terrain_offset if is_left else self.right_terrain_offset
        # Enquanto a redistribuicao entra, retira suavemente a compensacao
        # lateral comum. Sem isso, ela encurta tambem as quatro patas que devem
        # ganhar contato com o fundo do duto.
        pipe_mix = clamp(
            self.lateral_relief / max(MIN_PIPE_LATERAL_RELIEF, 1e-6),
            0.0,
            1.0,
        )
        pipe_influence = 1.0 - pipe_mix * (1.0 - PIPE_TERRAIN_INFLUENCE)
        return offset * self.terrain_blend * pipe_influence

    def _pipe_relief_for_leg(self, leg):
        """Descarrega as duas extremas e transfere apoio para as outras quatro."""
        if leg in self.lateral_relief_legs:
            return PIPE_RELIEF_SIGN * self.lateral_relief

        support_extension = min(
            MAX_PIPE_SUPPORT_EXTENSION,
            PIPE_SUPPORT_EXTENSION_RATIO * self.lateral_relief,
        )
        return -PIPE_RELIEF_SIGN * support_extension

    def gait_step(self):
        """Avanca, adapta o pouso e corrige continuamente o rumo pelo yaw."""
        self._ensure_simulation_running()
        dt = self.sim.getSimulationTimeStep()
        self.movement_strength = min(1.0, self.movement_strength + dt * 0.5)
        self.travel_command = move_toward(
            self.travel_command,
            self.target_travel_command,
            DIRECTION_CHANGE_RATE * dt,
        )
        travel_strength = abs(self.travel_command)
        turn_strength = 1.0 if self.navigation_turning else travel_strength
        gait_strength = self.movement_strength * max(travel_strength, turn_strength)
        center_x = sum(foot[0] for foot in self.initial_feet) / 6.0
        center_y = sum(foot[1] for foot in self.initial_feet) / 6.0

        # Durante o apoio, o corpo reage no sentido oposto ao deslocamento dos
        # alvos. Por isso o comando tangencial das patas recebe sinal negativo.
        turn_mix = -HEADING_CORRECTION_SIGN * self.heading_steer

        for leg in range(6):
            phase = (
                self.step_progression + (self.leg_movement_index[leg] - 1) / 6.0
            ) % 1.0
            relative_phase = (phase - 1.0 / 3.0) % 1.0

            if relative_phase < SWING_FRACTION:
                u = relative_phase / SWING_FRACTION
                stride_offset = WALK_AMPLITUDE / 2.0 - WALK_AMPLITUDE * u
                offset_z = WALK_STEP_HEIGHT * math.sin(math.pi * u)
            else:
                stance = (relative_phase - SWING_FRACTION) / (1.0 - SWING_FRACTION)
                stride_offset = -WALK_AMPLITUDE / 2.0 + WALK_AMPLITUDE * stance
                offset_z = 0.0

            initial = self.initial_feet[leg]
            relative_x = initial[0] - center_x
            relative_y = initial[1] - center_y
            radius = max(math.hypot(relative_x, relative_y), 1e-6)
            tangent_x = -relative_y / radius
            tangent_y = relative_x / radius
            target = [
                initial[0]
                + stride_offset
                * turn_mix
                * tangent_x
                * self.movement_strength
                * turn_strength,
                initial[1]
                + stride_offset
                * (
                    FORWARD_Y_SIGN * self.travel_command
                    + turn_mix * turn_strength * tangent_y
                )
                * self.movement_strength,
                initial[2]
                + offset_z * gait_strength
                + self._terrain_offset_for_leg(leg)
                + self._pipe_relief_for_leg(leg)
                + self.leg_balance_correction[leg],
            ]
            self.sim.setObjectPosition(self.leg_targets[leg], target, self.leg_base)

        self.simIK.handleGroup(
            self.ik_env,
            self.ik_group,
            {"syncWorlds": True, "allowError": True},
        )
        self.step_progression += dt * WALK_VEL

    def walk_blind(self, run_seconds=None):
        """Anda sempre para frente; sensores alteram somente postura e passada."""
        start = self.sim.getSimulationTime()
        while run_seconds is None or self.sim.getSimulationTime() - start < run_seconds:
            self.control_step(manage_legacy_events=True)

    def control_step(self, manage_legacy_events=False):
        """Executa um ciclo fisico; o cerebro externo decide os comandos de marcha."""
        self._ensure_simulation_running()
        self._update_front_sensor_test(manage_legacy_return=manage_legacy_events)
        self._update_up_sensor_test()
        if manage_legacy_events:
            self._update_return_from_debris()
        self._update_terrain_profile()
        self._update_posture()
        self.gait_step()
        self._advance_sim()

    def _advance_sim(self):
        self._ensure_simulation_running()
        if SYNC_MODE:
            self.sim.step()
        else:
            time.sleep(max(self.sim.getSimulationTimeStep(), 0.001))


def main():
    robot = HexapodController()
    sim = robot.sim

    if SYNC_MODE:
        sim.setStepping(True)

    # Uma parada pode ser assincrona. Aguarda a restauracao completa da cena
    # anterior antes de registrar qualquer posicao como sendo a inicial.
    robot.ensure_simulation_stopped()
    robot.init()
    sim.startSimulation()
    try:
        robot.reset_to_initial_pose()
        robot.settle_and_calibrate()
        robot.walk_blind()
    except SimulationStoppedManually as exc:
        print(f"{exc} Controlador encerrado sem novos movimentos.")
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuario.")
    finally:
        robot.ensure_simulation_stopped()
        print("Simulacao parada.")


if __name__ == "__main__":
    main()
