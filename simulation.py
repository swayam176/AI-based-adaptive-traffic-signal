import random
import time
import threading
import pygame
import sys
import math
import os
import csv
from datetime import datetime

# ─────────────────────────────────────────────
#  AI Traffic Management System – Configuration
# ─────────────────────────────────────────────
defaultYellow     = 5       # fixed 5-second yellow buffer (always enforced)
defaultRed        = 150     # initial red placeholder (overwritten each cycle)
MIN_GREEN         = 8       # minimum green time (seconds)
MAX_GREEN         = 40      # maximum green time (seconds)
PER_VEHICLE_SEC   = 2       # extra seconds of green per waiting vehicle
FIXED_GREEN       = 20      # fixed-time mode green duration

# Fairness / starvation-prevention settings
STARVATION_BONUS      = 3   # phantom vehicles added to score per skipped cycle
MAX_WAIT_CYCLES       = 3   # after this many skips a direction is forced green
EARLY_EXIT_THRESHOLD  = 2   # stop green when fewer than 3 vehicles remain
EARLY_EXIT_MIN_SERVED = 5   # minimum seconds served before early exit is allowed

# ── Simulation modes ──────────────────────────────────────────────────────────
MODE_MENU      = "MENU"        # mode-selection screen
MODE_FIXED     = "FIXED"       # fixed-time signal control
MODE_AI        = "AI"          # AI adaptive signal control
MODE_ANALYTICS = "ANALYTICS"   # analytics dashboard
MODE_RESULTS   = "RESULTS"     # final comparison results

# Scenario replay seed (guarantees same traffic for both modes)
SCENARIO_SEED  = 42
SIM_DURATION   = 90            # seconds per test run

# ── No-parking box zones ──────────────────────────────────────────────────────
NO_PARKING_ZONES = [
    (pygame.Rect(160, 300, 65, 34), "right"),
    (pygame.Rect(370, 508, 65, 34), "right"),
    (pygame.Rect(900, 300, 65, 34), "left"),
]

PARKED_VEHICLES = [
    (162, 303, 'right', 'car'),
    (902, 303, 'left',  'car'),
]

defaultGreen = {0: MIN_GREEN, 1: MIN_GREEN, 2: MIN_GREEN, 3: MIN_GREEN}

signals        = []
noOfSignals    = 4
currentGreen   = 0
nextGreen      = (currentGreen + 1) % noOfSignals
currentYellow  = 0

# AI state
ai_vehicle_counts  = [0, 0, 0, 0]
ai_green_times     = [MIN_GREEN] * 4
ai_next_choice     = -1
ai_log             = []
wait_cycles        = [0, 0, 0, 0]

speeds = {'car': 2.25, 'bus': 1.8, 'truck': 1.8, 'bike': 2.5}

x = {'right': [0, 0, 0],       'down': [755, 727, 697],
     'left':  [1400, 1400, 1400], 'up': [602, 627, 657]}
y = {'right': [348, 370, 398], 'down': [0, 0, 0],
     'left':  [498, 466, 436], 'up': [800, 800, 800]}

vehicles = {
    'right': {0: [], 1: [], 2: [], 'crossed': 0},
    'down':  {0: [], 1: [], 2: [], 'crossed': 0},
    'left':  {0: [], 1: [], 2: [], 'crossed': 0},
    'up':    {0: [], 1: [], 2: [], 'crossed': 0},
}
vehicleTypes     = {0: 'car', 1: 'bus', 2: 'truck', 3: 'bike'}
directionNumbers = {0: 'right', 1: 'down', 2: 'left', 3: 'up'}

signalCoods      = [(530, 230), (810, 230), (810, 570), (530, 570)]
signalTimerCoods = [(530, 210), (810, 210), (810, 550), (530, 550)]

stopLines   = {'right': 590, 'down': 330, 'left': 800, 'up': 535}
defaultStop = {'right': 580, 'down': 320, 'left': 810, 'up': 545}

stoppingGap = 25
movingGap   = 25

allowedVehicleTypes     = {'car': True, 'bus': True, 'truck': True, 'bike': True}
allowedVehicleTypesList = []

vehiclesTurned    = {'right': {1: [], 2: []}, 'down': {1: [], 2: []},
                     'left':  {1: [], 2: []}, 'up':   {1: [], 2: []}}
vehiclesNotTurned = {'right': {1: [], 2: []}, 'down': {1: [], 2: []},
                     'left':  {1: [], 2: []}, 'up':   {1: [], 2: []}}
rotationAngle = 3
mid = {
    'right': {'x': 705, 'y': 445}, 'down':  {'x': 695, 'y': 450},
    'left':  {'x': 695, 'y': 425}, 'up':    {'x': 695, 'y': 400},
}

# ── Global simulation control flags ──────────────────────────────────────────
sim_mode          = MODE_MENU      # current application mode
sim_paused        = False          # pause flag
sim_running       = False          # a test run is active
sim_reset_event   = threading.Event()   # triggers a clean reset
mode_switch_lock  = threading.Lock()    # guards mode transitions

# ── Metrics / analytics state ─────────────────────────────────────────────────
# Per-vehicle wait tracking: {vehicle_id: start_wait_time}
_wait_start: dict = {}
_wait_lock  = threading.Lock()

# Accumulated stats for current run
stats = {
    'generated':     0,
    'served':        0,
    'total_wait':    0.0,   # sum of all wait durations (seconds)
    'max_wait':      0.0,
    'wait_samples':  0,
    'queue_sum':     0.0,   # sum of queue-length observations
    'queue_obs':     0,     # number of observations
    'max_queue':     0,
    'dir_generated': [0, 0, 0, 0],
    'dir_served':    [0, 0, 0, 0],
    'dir_wait_sum':  [0.0, 0.0, 0.0, 0.0],
    'dir_wait_cnt':  [0, 0, 0, 0],
    'dir_queue':     [0, 0, 0, 0],
    'sim_elapsed':   0.0,
    'sim_start':     None,
}

# Completed run archives
completed_fixed = None   # stats dict saved after fixed-time run
completed_ai    = None   # stats dict saved after AI run

# Time-series recording for CSV export
timeseries_log = []   # list of dicts

# Scenario replay: list of (rel_time, lane, vtype_idx, dir_idx, will_turn)
_scenario_events   = []
_scenario_generated = False

# ── Controller thread handle ──────────────────────────────────────────────────
_controller_thread  = None
_generator_thread   = None
_stop_controller    = threading.Event()
_stop_generator     = threading.Event()

# Current signal green-time source (for display)
current_green_time = FIXED_GREEN

pygame.init()
simulation = pygame.sprite.Group()

# ─────────────────────────────────────────────
#  Traffic Signal class
# ─────────────────────────────────────────────
class TrafficSignal:
    def __init__(self, red, yellow, green):
        self.red        = red
        self.yellow     = yellow
        self.green      = green
        self.signalText = ""
        self.vehicleCount = 0


# ─────────────────────────────────────────────
#  Vehicle class (original movement logic preserved)
# ─────────────────────────────────────────────
class Vehicle(pygame.sprite.Sprite):
    def __init__(self, lane, vehicleClass, direction_number, direction, will_turn):
        pygame.sprite.Sprite.__init__(self)
        self.lane             = lane
        self.vehicleClass     = vehicleClass
        self.speed            = speeds[vehicleClass]
        self.direction_number = direction_number
        self.direction        = direction
        self.x                = x[direction][lane]
        self.y                = y[direction][lane]
        self.crossed          = 0
        self.willTurn         = will_turn
        self.turned           = 0
        self.rotateAngle      = 0
        self.crossedIndex     = 0
        self._wait_accum      = 0.0   # total accumulated wait (seconds)
        self._is_waiting      = False
        self._wait_start_ts   = None
        self._served_counted  = False
        self._dir_idx         = direction_number
        vehicles[direction][lane].append(self)
        self.index = len(vehicles[direction][lane]) - 1

        path = "images/" + direction + "/" + vehicleClass + ".png"
        self.originalImage = pygame.image.load(path)
        self.image         = pygame.image.load(path)

        if (len(vehicles[direction][lane]) > 1 and
                vehicles[direction][lane][self.index - 1].crossed == 0):
            if direction == 'right':
                self.stop = (vehicles[direction][lane][self.index - 1].stop
                             - vehicles[direction][lane][self.index - 1].image.get_rect().width
                             - stoppingGap)
            elif direction == 'left':
                self.stop = (vehicles[direction][lane][self.index - 1].stop
                             + vehicles[direction][lane][self.index - 1].image.get_rect().width
                             + stoppingGap)
            elif direction == 'down':
                self.stop = (vehicles[direction][lane][self.index - 1].stop
                             - vehicles[direction][lane][self.index - 1].image.get_rect().height
                             - stoppingGap)
            elif direction == 'up':
                self.stop = (vehicles[direction][lane][self.index - 1].stop
                             + vehicles[direction][lane][self.index - 1].image.get_rect().height
                             + stoppingGap)
        else:
            self.stop = defaultStop[direction]

        if direction == 'right':
            x[direction][lane] -= self.image.get_rect().width + stoppingGap
        elif direction == 'left':
            x[direction][lane] += self.image.get_rect().width + stoppingGap
        elif direction == 'down':
            y[direction][lane] -= self.image.get_rect().height + stoppingGap
        elif direction == 'up':
            y[direction][lane] += self.image.get_rect().height + stoppingGap
        simulation.add(self)

        # Track generation
        stats['generated'] += 1
        stats['dir_generated'][direction_number] += 1

    def _begin_wait(self):
        if not self._is_waiting:
            self._is_waiting   = True
            self._wait_start_ts = time.time()

    def _end_wait(self):
        if self._is_waiting and self._wait_start_ts is not None:
            elapsed = time.time() - self._wait_start_ts
            self._wait_accum += elapsed
            self._is_waiting  = False
            self._wait_start_ts = None
            # Record to stats
            stats['total_wait'] += elapsed
            stats['wait_samples'] += 1
            if elapsed > stats['max_wait']:
                stats['max_wait'] = elapsed
            stats['dir_wait_sum'][self._dir_idx] += elapsed
            stats['dir_wait_cnt'][self._dir_idx] += 1

    def render(self, screen):
        screen.blit(self.image, (self.x, self.y))

    def move(self):
        if sim_paused:
            # Keep accumulating wait time even when paused (paused = real time pauses)
            return

        if self.direction == 'right':
            if self.crossed == 0 and self.x + self.image.get_rect().width > stopLines[self.direction]:
                self.crossed = 1
                vehicles[self.direction]['crossed'] += 1
                if self.willTurn == 0:
                    vehiclesNotTurned[self.direction][self.lane].append(self)
                    self.crossedIndex = len(vehiclesNotTurned[self.direction][self.lane]) - 1
            if self.willTurn == 1:
                if self.lane == 1:
                    if self.crossed == 0 or self.x + self.image.get_rect().width < stopLines[self.direction] + 40:
                        if ((self.x + self.image.get_rect().width <= self.stop or (currentGreen == 0 and currentYellow == 0) or self.crossed == 1) and
                                (self.index == 0 or self.x + self.image.get_rect().width < (vehicles[self.direction][self.lane][self.index - 1].x - movingGap) or
                                 vehicles[self.direction][self.lane][self.index - 1].turned == 1)):
                            self._check_waiting(True)
                            self.x += self.speed
                        else:
                            self._check_waiting(False)
                    else:
                        if self.turned == 0:
                            self.rotateAngle += rotationAngle
                            self.image = pygame.transform.rotate(self.originalImage, self.rotateAngle)
                            self.x += 2.4
                            self.y -= 2.8
                            if self.rotateAngle == 90:
                                self.turned = 1
                                vehiclesTurned[self.direction][self.lane].append(self)
                                self.crossedIndex = len(vehiclesTurned[self.direction][self.lane]) - 1
                        else:
                            if (self.crossedIndex == 0 or
                                    self.y > (vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].y +
                                              vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].image.get_rect().height + movingGap)):
                                self.y -= self.speed
                elif self.lane == 2:
                    if self.crossed == 0 or self.x + self.image.get_rect().width < mid[self.direction]['x']:
                        if ((self.x + self.image.get_rect().width <= self.stop or (currentGreen == 0 and currentYellow == 0) or self.crossed == 1) and
                                (self.index == 0 or self.x + self.image.get_rect().width < (vehicles[self.direction][self.lane][self.index - 1].x - movingGap) or
                                 vehicles[self.direction][self.lane][self.index - 1].turned == 1)):
                            self._check_waiting(True)
                            self.x += self.speed
                        else:
                            self._check_waiting(False)
                    else:
                        if self.turned == 0:
                            self.rotateAngle += rotationAngle
                            self.image = pygame.transform.rotate(self.originalImage, -self.rotateAngle)
                            self.x += 2
                            self.y += 1.8
                            if self.rotateAngle == 90:
                                self.turned = 1
                                vehiclesTurned[self.direction][self.lane].append(self)
                                self.crossedIndex = len(vehiclesTurned[self.direction][self.lane]) - 1
                        else:
                            if (self.crossedIndex == 0 or
                                    (self.y + self.image.get_rect().height) < (vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].y - movingGap)):
                                self.y += self.speed
            else:
                if self.crossed == 0:
                    can_move = ((self.x + self.image.get_rect().width <= self.stop or (currentGreen == 0 and currentYellow == 0)) and
                                (self.index == 0 or self.x + self.image.get_rect().width < (vehicles[self.direction][self.lane][self.index - 1].x - movingGap)))
                    self._check_waiting(can_move)
                    if can_move:
                        self.x += self.speed
                else:
                    if (self.crossedIndex == 0 or
                            self.x + self.image.get_rect().width < (vehiclesNotTurned[self.direction][self.lane][self.crossedIndex - 1].x - movingGap)):
                        self.x += self.speed

        elif self.direction == 'down':
            if self.crossed == 0 and self.y + self.image.get_rect().height > stopLines[self.direction]:
                self.crossed = 1
                vehicles[self.direction]['crossed'] += 1
                if self.willTurn == 0:
                    vehiclesNotTurned[self.direction][self.lane].append(self)
                    self.crossedIndex = len(vehiclesNotTurned[self.direction][self.lane]) - 1
            if self.willTurn == 1:
                if self.lane == 1:
                    if self.crossed == 0 or self.y + self.image.get_rect().height < stopLines[self.direction] + 50:
                        if ((self.y + self.image.get_rect().height <= self.stop or (currentGreen == 1 and currentYellow == 0) or self.crossed == 1) and
                                (self.index == 0 or self.y + self.image.get_rect().height < (vehicles[self.direction][self.lane][self.index - 1].y - movingGap) or
                                 vehicles[self.direction][self.lane][self.index - 1].turned == 1)):
                            self._check_waiting(True)
                            self.y += self.speed
                        else:
                            self._check_waiting(False)
                    else:
                        if self.turned == 0:
                            self.rotateAngle += rotationAngle
                            self.image = pygame.transform.rotate(self.originalImage, self.rotateAngle)
                            self.x += 1.2
                            self.y += 1.8
                            if self.rotateAngle == 90:
                                self.turned = 1
                                vehiclesTurned[self.direction][self.lane].append(self)
                                self.crossedIndex = len(vehiclesTurned[self.direction][self.lane]) - 1
                        else:
                            if (self.crossedIndex == 0 or
                                    (self.x + self.image.get_rect().width) < (vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].x - movingGap)):
                                self.x += self.speed
                elif self.lane == 2:
                    if self.crossed == 0 or self.y + self.image.get_rect().height < mid[self.direction]['y']:
                        if ((self.y + self.image.get_rect().height <= self.stop or (currentGreen == 1 and currentYellow == 0) or self.crossed == 1) and
                                (self.index == 0 or self.y + self.image.get_rect().height < (vehicles[self.direction][self.lane][self.index - 1].y - movingGap) or
                                 vehicles[self.direction][self.lane][self.index - 1].turned == 1)):
                            self._check_waiting(True)
                            self.y += self.speed
                        else:
                            self._check_waiting(False)
                    else:
                        if self.turned == 0:
                            self.rotateAngle += rotationAngle
                            self.image = pygame.transform.rotate(self.originalImage, -self.rotateAngle)
                            self.x -= 2.5
                            self.y += 2
                            if self.rotateAngle == 90:
                                self.turned = 1
                                vehiclesTurned[self.direction][self.lane].append(self)
                                self.crossedIndex = len(vehiclesTurned[self.direction][self.lane]) - 1
                        else:
                            if (self.crossedIndex == 0 or
                                    self.x > (vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].x +
                                              vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].image.get_rect().width + movingGap)):
                                self.x -= self.speed
            else:
                if self.crossed == 0:
                    can_move = ((self.y + self.image.get_rect().height <= self.stop or (currentGreen == 1 and currentYellow == 0)) and
                                (self.index == 0 or self.y + self.image.get_rect().height < (vehicles[self.direction][self.lane][self.index - 1].y - movingGap)))
                    self._check_waiting(can_move)
                    if can_move:
                        self.y += self.speed
                else:
                    if (self.crossedIndex == 0 or
                            self.y + self.image.get_rect().height < (vehiclesNotTurned[self.direction][self.lane][self.crossedIndex - 1].y - movingGap)):
                        self.y += self.speed

        elif self.direction == 'left':
            if self.crossed == 0 and self.x < stopLines[self.direction]:
                self.crossed = 1
                vehicles[self.direction]['crossed'] += 1
                if self.willTurn == 0:
                    vehiclesNotTurned[self.direction][self.lane].append(self)
                    self.crossedIndex = len(vehiclesNotTurned[self.direction][self.lane]) - 1
            if self.willTurn == 1:
                if self.lane == 1:
                    if self.crossed == 0 or self.x > stopLines[self.direction] - 70:
                        if ((self.x >= self.stop or (currentGreen == 2 and currentYellow == 0) or self.crossed == 1) and
                                (self.index == 0 or self.x > (vehicles[self.direction][self.lane][self.index - 1].x +
                                                              vehicles[self.direction][self.lane][self.index - 1].image.get_rect().width + movingGap) or
                                 vehicles[self.direction][self.lane][self.index - 1].turned == 1)):
                            self._check_waiting(True)
                            self.x -= self.speed
                        else:
                            self._check_waiting(False)
                    else:
                        if self.turned == 0:
                            self.rotateAngle += rotationAngle
                            self.image = pygame.transform.rotate(self.originalImage, self.rotateAngle)
                            self.x -= 1
                            self.y += 1.2
                            if self.rotateAngle == 90:
                                self.turned = 1
                                vehiclesTurned[self.direction][self.lane].append(self)
                                self.crossedIndex = len(vehiclesTurned[self.direction][self.lane]) - 1
                        else:
                            if (self.crossedIndex == 0 or
                                    (self.y + self.image.get_rect().height) < (vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].y - movingGap)):
                                self.y += self.speed
                elif self.lane == 2:
                    if self.crossed == 0 or self.x > mid[self.direction]['x']:
                        if ((self.x >= self.stop or (currentGreen == 2 and currentYellow == 0) or self.crossed == 1) and
                                (self.index == 0 or self.x > (vehicles[self.direction][self.lane][self.index - 1].x +
                                                              vehicles[self.direction][self.lane][self.index - 1].image.get_rect().width + movingGap) or
                                 vehicles[self.direction][self.lane][self.index - 1].turned == 1)):
                            self._check_waiting(True)
                            self.x -= self.speed
                        else:
                            self._check_waiting(False)
                    else:
                        if self.turned == 0:
                            self.rotateAngle += rotationAngle
                            self.image = pygame.transform.rotate(self.originalImage, -self.rotateAngle)
                            self.x -= 1.8
                            self.y -= 2.5
                            if self.rotateAngle == 90:
                                self.turned = 1
                                vehiclesTurned[self.direction][self.lane].append(self)
                                self.crossedIndex = len(vehiclesTurned[self.direction][self.lane]) - 1
                        else:
                            if (self.crossedIndex == 0 or
                                    self.y > (vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].y +
                                              vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].image.get_rect().height + movingGap)):
                                self.y -= self.speed
            else:
                if self.crossed == 0:
                    can_move = ((self.x >= self.stop or (currentGreen == 2 and currentYellow == 0)) and
                                (self.index == 0 or self.x > (vehicles[self.direction][self.lane][self.index - 1].x +
                                                              vehicles[self.direction][self.lane][self.index - 1].image.get_rect().width + movingGap)))
                    self._check_waiting(can_move)
                    if can_move:
                        self.x -= self.speed
                else:
                    if (self.crossedIndex == 0 or
                            self.x > (vehiclesNotTurned[self.direction][self.lane][self.crossedIndex - 1].x +
                                      vehiclesNotTurned[self.direction][self.lane][self.crossedIndex - 1].image.get_rect().width + movingGap)):
                        self.x -= self.speed

        elif self.direction == 'up':
            if self.crossed == 0 and self.y < stopLines[self.direction]:
                self.crossed = 1
                vehicles[self.direction]['crossed'] += 1
                if self.willTurn == 0:
                    vehiclesNotTurned[self.direction][self.lane].append(self)
                    self.crossedIndex = len(vehiclesNotTurned[self.direction][self.lane]) - 1
            if self.willTurn == 1:
                if self.lane == 1:
                    if self.crossed == 0 or self.y > stopLines[self.direction] - 60:
                        if ((self.y >= self.stop or (currentGreen == 3 and currentYellow == 0) or self.crossed == 1) and
                                (self.index == 0 or self.y > (vehicles[self.direction][self.lane][self.index - 1].y +
                                                              vehicles[self.direction][self.lane][self.index - 1].image.get_rect().height + movingGap) or
                                 vehicles[self.direction][self.lane][self.index - 1].turned == 1)):
                            self._check_waiting(True)
                            self.y -= self.speed
                        else:
                            self._check_waiting(False)
                    else:
                        if self.turned == 0:
                            self.rotateAngle += rotationAngle
                            self.image = pygame.transform.rotate(self.originalImage, self.rotateAngle)
                            self.x -= 2
                            self.y -= 1.2
                            if self.rotateAngle == 90:
                                self.turned = 1
                                vehiclesTurned[self.direction][self.lane].append(self)
                                self.crossedIndex = len(vehiclesTurned[self.direction][self.lane]) - 1
                        else:
                            if (self.crossedIndex == 0 or
                                    self.x > (vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].x +
                                              vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].image.get_rect().width + movingGap)):
                                self.x -= self.speed
                elif self.lane == 2:
                    if self.crossed == 0 or self.y > mid[self.direction]['y']:
                        if ((self.y >= self.stop or (currentGreen == 3 and currentYellow == 0) or self.crossed == 1) and
                                (self.index == 0 or self.y > (vehicles[self.direction][self.lane][self.index - 1].y +
                                                              vehicles[self.direction][self.lane][self.index - 1].image.get_rect().height + movingGap) or
                                 vehicles[self.direction][self.lane][self.index - 1].turned == 1)):
                            self._check_waiting(True)
                            self.y -= self.speed
                        else:
                            self._check_waiting(False)
                    else:
                        if self.turned == 0:
                            self.rotateAngle += rotationAngle
                            self.image = pygame.transform.rotate(self.originalImage, -self.rotateAngle)
                            self.x += 1
                            self.y -= 1
                            if self.rotateAngle == 90:
                                self.turned = 1
                                vehiclesTurned[self.direction][self.lane].append(self)
                                self.crossedIndex = len(vehiclesTurned[self.direction][self.lane]) - 1
                        else:
                            if (self.crossedIndex == 0 or
                                    self.x < (vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].x -
                                              vehiclesTurned[self.direction][self.lane][self.crossedIndex - 1].image.get_rect().width - movingGap)):
                                self.x += self.speed
            else:
                if self.crossed == 0:
                    can_move = ((self.y >= self.stop or (currentGreen == 3 and currentYellow == 0)) and
                                (self.index == 0 or self.y > (vehicles[self.direction][self.lane][self.index - 1].y +
                                                              vehicles[self.direction][self.lane][self.index - 1].image.get_rect().height + movingGap)))
                    self._check_waiting(can_move)
                    if can_move:
                        self.y -= self.speed
                else:
                    if (self.crossedIndex == 0 or
                            self.y > (vehiclesNotTurned[self.direction][self.lane][self.crossedIndex - 1].y +
                                      vehiclesNotTurned[self.direction][self.lane][self.crossedIndex - 1].image.get_rect().height + movingGap)):
                        self.y -= self.speed

        # Mark as served when it exits the screen
        self._check_served()

    def _check_waiting(self, moving: bool):
        """Update wait tracking based on whether the vehicle is currently moving."""
        if not moving:
            self._begin_wait()
        else:
            self._end_wait()

    def _check_served(self):
        """Count this vehicle exactly once when it leaves the visible screen area."""
        if self._served_counted:
            return
        off_screen = False
        if self.direction == 'right'  and self.x > 1450: off_screen = True
        if self.direction == 'left'   and self.x + self.image.get_rect().width < -50: off_screen = True
        if self.direction == 'down'   and self.y > 850: off_screen = True
        if self.direction == 'up'     and self.y + self.image.get_rect().height < -50: off_screen = True
        # Also count turning vehicles that have moved off-screen
        if self.turned == 1:
            if self.direction in ('right',) and self.y + self.image.get_rect().height < -50: off_screen = True
            if self.direction in ('right',) and self.y > 850: off_screen = True
            if self.direction in ('left',)  and self.y + self.image.get_rect().height < -50: off_screen = True
            if self.direction in ('left',)  and self.y > 850: off_screen = True
            if self.direction in ('down',)  and self.x > 1450: off_screen = True
            if self.direction in ('down',)  and self.x + self.image.get_rect().width < -50: off_screen = True
            if self.direction in ('up',)    and self.x > 1450: off_screen = True
            if self.direction in ('up',)    and self.x + self.image.get_rect().width < -50: off_screen = True
        if off_screen:
            self._served_counted = True
            self._end_wait()   # close any open wait interval
            stats['served'] += 1
            stats['dir_served'][self._dir_idx] += 1


# ─────────────────────────────────────────────
#  AI Core Functions (original, preserved)
# ─────────────────────────────────────────────
def countWaitingVehicles(directionIndex):
    direction = directionNumbers[directionIndex]
    count = 0
    try:
        for lane in range(0, 3):
            for vehicle in list(vehicles[direction][lane]):
                if vehicle.crossed == 0:
                    count += 1
    except Exception:
        pass
    return count


def aiUpdateCounts():
    global ai_vehicle_counts
    for i in range(noOfSignals):
        ai_vehicle_counts[i] = countWaitingVehicles(i)
        signals[i].vehicleCount = ai_vehicle_counts[i]


def aiSelectNextGreen():
    global ai_next_choice, wait_cycles
    aiUpdateCounts()
    forced = [i for i in range(noOfSignals)
              if i != currentGreen and wait_cycles[i] >= MAX_WAIT_CYCLES]
    if forced:
        chosen = max(forced, key=lambda k: ai_vehicle_counts[k])
    else:
        scores = {
            i: ai_vehicle_counts[i] + STARVATION_BONUS * wait_cycles[i]
            for i in range(noOfSignals) if i != currentGreen
        }
        chosen = max(scores, key=lambda k: scores[k])

    for i in range(noOfSignals):
        if i == chosen:
            wait_cycles[i] = 0
        elif i != currentGreen:
            wait_cycles[i] += 1

    ai_next_choice = chosen
    return chosen


def aiComputeGreenTime(directionIndex):
    count = countWaitingVehicles(directionIndex)
    green = MIN_GREEN + count * PER_VEHICLE_SEC
    green = max(MIN_GREEN, min(MAX_GREEN, green))
    ai_green_times[directionIndex] = green
    return green


def aiLogDecision(chosen, green_time):
    direction = directionNumbers[chosen]
    count     = ai_vehicle_counts[chosen]
    entry     = f">> {direction.upper()} | {count} vehicles | {green_time}s green"
    ai_log.append(entry)
    if len(ai_log) > 5:
        ai_log.pop(0)


# ─────────────────────────────────────────────
#  Signal Initialization
# ─────────────────────────────────────────────
def initialize_signals():
    """Create 4 signals. Green time depends on current mode."""
    global signals
    signals.clear()
    if sim_mode == MODE_AI:
        g0 = aiComputeGreenTime(0)
        ts1 = TrafficSignal(0, defaultYellow, g0)
        signals.append(ts1)
        g1 = aiComputeGreenTime(1)
        ts2 = TrafficSignal(ts1.red + ts1.yellow + ts1.green, defaultYellow, g1)
        signals.append(ts2)
        ts3 = TrafficSignal(defaultRed, defaultYellow, aiComputeGreenTime(2))
        signals.append(ts3)
        ts4 = TrafficSignal(defaultRed, defaultYellow, aiComputeGreenTime(3))
        signals.append(ts4)
        aiLogDecision(0, g0)
    else:
        # Fixed-time: all signals start with fixed green, sequential red
        ts1 = TrafficSignal(0, defaultYellow, FIXED_GREEN)
        signals.append(ts1)
        ts2 = TrafficSignal(ts1.red + ts1.yellow + ts1.green, defaultYellow, FIXED_GREEN)
        signals.append(ts2)
        signals.append(TrafficSignal(defaultRed, defaultYellow, FIXED_GREEN))
        signals.append(TrafficSignal(defaultRed, defaultYellow, FIXED_GREEN))


# ─────────────────────────────────────────────
#  Timer updater (called every second by controller)
# ─────────────────────────────────────────────
def updateValues():
    for i in range(0, noOfSignals):
        if i == currentGreen:
            if currentYellow == 0:
                signals[i].green  = max(0, signals[i].green  - 1)
            else:
                signals[i].yellow = max(0, signals[i].yellow - 1)
        else:
            signals[i].red = max(0, signals[i].red - 1)


def _sleep_accurate(seconds):
    """Sleep accurately, respecting pause state."""
    deadline = time.time() + seconds
    while True:
        if _stop_controller.is_set():
            return
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        if not sim_paused:
            time.sleep(min(remaining, 0.05))
        else:
            time.sleep(0.05)
            deadline += 0.05  # don't burn paused time


# ─────────────────────────────────────────────
#  AI Adaptive Controller Thread
# ─────────────────────────────────────────────
def ai_controller():
    global currentGreen, currentYellow, nextGreen, current_green_time
    initialize_signals()

    while not _stop_controller.is_set():
        # GREEN PHASE
        aiUpdateCounts()
        fresh_count = ai_vehicle_counts[currentGreen]
        computed_green = max(MIN_GREEN, min(MAX_GREEN, MIN_GREEN + fresh_count * PER_VEHICLE_SEC))
        signals[currentGreen].green = computed_green
        ai_green_times[currentGreen] = computed_green
        current_green_time = computed_green

        direction = directionNumbers[currentGreen]
        waiting_snap = set()
        try:
            for lane in range(3):
                for v in list(vehicles[direction][lane]):
                    if v.crossed == 0:
                        waiting_snap.add(id(v))
        except Exception:
            pass

        served_seconds = 0
        while signals[currentGreen].green > 0 and not _stop_controller.is_set():
            tick_start = time.time()
            aiUpdateCounts()
            updateValues()
            _sleep_accurate(max(0.0, 1.0 - (time.time() - tick_start)))
            served_seconds += 1

            if served_seconds >= EARLY_EXIT_MIN_SERVED and waiting_snap:
                try:
                    still_waiting = sum(
                        1 for lane in range(3)
                        for v in list(vehicles[direction][lane])
                        if id(v) in waiting_snap and v.crossed == 0
                    )
                except Exception:
                    still_waiting = 99
                if still_waiting < 3:
                    signals[currentGreen].green = 0
                    break

        if _stop_controller.is_set():
            break

        # YELLOW PHASE
        currentYellow = 1
        signals[currentGreen].yellow = defaultYellow
        for i in range(0, 3):
            for vehicle in list(vehicles[directionNumbers[currentGreen]][i]):
                vehicle.stop = defaultStop[directionNumbers[currentGreen]]
        while signals[currentGreen].yellow > 0 and not _stop_controller.is_set():
            tick_start = time.time()
            updateValues()
            _sleep_accurate(max(0.0, 1.0 - (time.time() - tick_start)))
        currentYellow = 0

        if _stop_controller.is_set():
            break

        signals[currentGreen].yellow = defaultYellow
        signals[currentGreen].red    = defaultRed

        nextGreen    = aiSelectNextGreen()
        newGreenTime = aiComputeGreenTime(nextGreen)
        signals[nextGreen].green = newGreenTime
        aiLogDecision(nextGreen, newGreenTime)
        current_green_time = newGreenTime

        for i in range(noOfSignals):
            if i != nextGreen:
                signals[i].red = signals[nextGreen].yellow + signals[nextGreen].green

        currentGreen = nextGreen


# ─────────────────────────────────────────────
#  Fixed-Time Controller Thread
# ─────────────────────────────────────────────
_fixed_sequence = [0, 1, 2, 3]   # round-robin direction order

def fixed_controller():
    global currentGreen, currentYellow, nextGreen, current_green_time
    initialize_signals()
    seq_idx = 0

    while not _stop_controller.is_set():
        currentGreen = _fixed_sequence[seq_idx % 4]
        aiUpdateCounts()   # keep vehicle-count display live

        signals[currentGreen].green = FIXED_GREEN
        current_green_time = FIXED_GREEN

        # GREEN PHASE
        while signals[currentGreen].green > 0 and not _stop_controller.is_set():
            tick_start = time.time()
            aiUpdateCounts()
            updateValues()
            _sleep_accurate(max(0.0, 1.0 - (time.time() - tick_start)))

        if _stop_controller.is_set():
            break

        # YELLOW PHASE
        currentYellow = 1
        signals[currentGreen].yellow = defaultYellow
        for i in range(0, 3):
            for vehicle in list(vehicles[directionNumbers[currentGreen]][i]):
                vehicle.stop = defaultStop[directionNumbers[currentGreen]]
        while signals[currentGreen].yellow > 0 and not _stop_controller.is_set():
            tick_start = time.time()
            updateValues()
            _sleep_accurate(max(0.0, 1.0 - (time.time() - tick_start)))
        currentYellow = 0

        if _stop_controller.is_set():
            break

        signals[currentGreen].yellow = defaultYellow
        signals[currentGreen].red    = defaultRed

        seq_idx += 1
        nextGreen = _fixed_sequence[seq_idx % 4]
        signals[nextGreen].green = FIXED_GREEN

        for i in range(noOfSignals):
            if i != nextGreen:
                signals[i].red = defaultYellow + FIXED_GREEN

        currentGreen = nextGreen


# ─────────────────────────────────────────────
#  Scenario: record & replay vehicle events
# ─────────────────────────────────────────────
def _generate_scenario():
    """Pre-generate a fixed list of vehicle spawn events for deterministic replay."""
    global _scenario_events, _scenario_generated
    rng = random.Random(SCENARIO_SEED)
    events = []
    t = 0.0
    while t < SIM_DURATION:
        interval = rng.uniform(0.8, 1.4)  # ~1 vehicle/second average
        t += interval
        if t >= SIM_DURATION:
            break
        vtype_idx = rng.choice([0, 1, 2, 3])
        lane      = rng.randint(1, 2)
        will_turn = 1 if (lane in (1, 2) and rng.randint(0, 99) < 40) else 0
        temp      = rng.randint(0, 99)
        dist = [25, 50, 75, 100]
        if   temp < dist[0]: dir_idx = 0
        elif temp < dist[1]: dir_idx = 1
        elif temp < dist[2]: dir_idx = 2
        else:                dir_idx = 3
        events.append((t, lane, vtype_idx, dir_idx, will_turn))
    _scenario_events    = events
    _scenario_generated = True


def _scenario_generator_thread():
    """Replay pre-recorded vehicle spawn events at the correct simulation times."""
    global _scenario_events
    if not _scenario_events:
        return
    sim_start = time.time()
    for (rel_t, lane, vtype_idx, dir_idx, will_turn) in _scenario_events:
        if _stop_generator.is_set():
            break
        # Wait until the correct simulation time
        target_wall = sim_start + rel_t
        while True:
            if _stop_generator.is_set():
                return
            remaining = target_wall - time.time()
            if remaining <= 0:
                break
            if not sim_paused:
                time.sleep(min(remaining, 0.05))
            else:
                time.sleep(0.05)
                sim_start += 0.05  # extend sim_start to not skip events during pause
        if _stop_generator.is_set():
            break
        try:
            Vehicle(lane, vehicleTypes[vtype_idx],
                    dir_idx, directionNumbers[dir_idx], will_turn)
        except Exception:
            pass


def _free_generator_thread():
    """Original free-running vehicle generator (used outside test runs)."""
    while not _stop_generator.is_set():
        if sim_paused:
            time.sleep(0.1)
            continue
        vehicle_type  = random.choice(allowedVehicleTypesList)
        lane_number   = random.randint(1, 2)
        will_turn     = 0
        if lane_number in (1, 2):
            if random.randint(0, 99) < 40:
                will_turn = 1
        temp = random.randint(0, 99)
        dist = [25, 50, 75, 100]
        if   temp < dist[0]: dir_idx = 0
        elif temp < dist[1]: dir_idx = 1
        elif temp < dist[2]: dir_idx = 2
        else:                dir_idx = 3
        try:
            Vehicle(lane_number, vehicleTypes[vehicle_type],
                    dir_idx, directionNumbers[dir_idx], will_turn)
        except Exception:
            pass
        time.sleep(1)


# ─────────────────────────────────────────────
#  Reset helpers
# ─────────────────────────────────────────────
def _reset_vehicles():
    """Clear all vehicles and reset spawn positions."""
    global vehicles, vehiclesTurned, vehiclesNotTurned, simulation
    for d in ['right', 'down', 'left', 'up']:
        for lane in range(3):
            vehicles[d][lane] = []
        vehicles[d]['crossed'] = 0
    for d in ['right', 'down', 'left', 'up']:
        for lane in (1, 2):
            vehiclesTurned[d][lane]    = []
            vehiclesNotTurned[d][lane] = []
    # Reset spawn x/y
    x['right'] = [0, 0, 0];         x['down']  = [755, 727, 697]
    x['left']  = [1400, 1400, 1400]; x['up']    = [602, 627, 657]
    y['right'] = [348, 370, 398];   y['down']  = [0, 0, 0]
    y['left']  = [498, 466, 436];   y['up']    = [800, 800, 800]
    simulation.empty()


def _reset_stats():
    """Zero all per-run analytics."""
    global stats, timeseries_log
    stats.update({
        'generated':     0,
        'served':        0,
        'total_wait':    0.0,
        'max_wait':      0.0,
        'wait_samples':  0,
        'queue_sum':     0.0,
        'queue_obs':     0,
        'max_queue':     0,
        'dir_generated': [0, 0, 0, 0],
        'dir_served':    [0, 0, 0, 0],
        'dir_wait_sum':  [0.0, 0.0, 0.0, 0.0],
        'dir_wait_cnt':  [0, 0, 0, 0],
        'dir_queue':     [0, 0, 0, 0],
        'sim_elapsed':   0.0,
        'sim_start':     None,
    })
    timeseries_log = []


def _reset_signal_state():
    global currentGreen, currentYellow, nextGreen, ai_vehicle_counts, ai_green_times
    global ai_next_choice, ai_log, wait_cycles, signals
    currentGreen   = 0
    currentYellow  = 0
    nextGreen      = 1
    ai_vehicle_counts = [0, 0, 0, 0]
    ai_green_times    = [MIN_GREEN] * 4
    ai_next_choice    = -1
    ai_log            = []
    wait_cycles       = [0, 0, 0, 0]
    signals.clear()


def stop_threads():
    """Stop controller and generator threads cleanly."""
    _stop_controller.set()
    _stop_generator.set()


def start_run(mode):
    """
    Start a new simulation run in the given mode.
    Stops existing threads, resets state, launches new threads.
    """
    global sim_mode, sim_running, _controller_thread, _generator_thread
    global _stop_controller, _stop_generator, sim_paused, stats

    sim_paused = False
    stop_threads()
    # Brief wait for threads to notice the stop event
    time.sleep(0.15)

    _stop_controller = threading.Event()
    _stop_generator  = threading.Event()

    _reset_vehicles()
    _reset_stats()
    _reset_signal_state()

    sim_mode = mode
    stats['sim_start'] = time.time()

    if mode in (MODE_AI, MODE_FIXED):
        if mode == MODE_AI:
            target_fn = ai_controller
        else:
            target_fn = fixed_controller
        _controller_thread = threading.Thread(target=target_fn, daemon=True)
        _controller_thread.start()

        _generator_thread = threading.Thread(target=_scenario_generator_thread, daemon=True)
        _generator_thread.start()
        sim_running = True


def reset_to_menu():
    global sim_mode, sim_running, sim_paused
    stop_threads()
    sim_paused  = False
    sim_running = False
    sim_mode    = MODE_MENU
    _reset_vehicles()
    _reset_signal_state()


# ─────────────────────────────────────────────
#  Queue-length sampling (called from render loop)
# ─────────────────────────────────────────────
_last_queue_sample = 0.0
QUEUE_SAMPLE_INTERVAL = 2.0  # seconds between queue observations

def _sample_queues():
    global _last_queue_sample
    now = time.time()
    if now - _last_queue_sample < QUEUE_SAMPLE_INTERVAL:
        return
    _last_queue_sample = now

    total_queue = 0
    for di, d in enumerate(['right', 'down', 'left', 'up']):
        q = 0
        try:
            for lane in range(3):
                for v in list(vehicles[d][lane]):
                    if v.crossed == 0:
                        q += 1
        except Exception:
            pass
        stats['dir_queue'][di] = q
        total_queue += q

    stats['queue_sum'] += total_queue
    stats['queue_obs'] += 1
    if total_queue > stats['max_queue']:
        stats['max_queue'] = total_queue

    # Time-series record
    if stats['sim_start'] is not None:
        elapsed = now - stats['sim_start']
        timeseries_log.append({
            'time':      round(elapsed, 1),
            'mode':      sim_mode,
            'queue_r':   stats['dir_queue'][0],
            'queue_d':   stats['dir_queue'][1],
            'queue_l':   stats['dir_queue'][2],
            'queue_u':   stats['dir_queue'][3],
            'total_q':   total_queue,
            'green_dir': currentGreen,
            'generated': stats['generated'],
            'served':    stats['served'],
        })

    # Update elapsed
    if stats['sim_start'] is not None:
        stats['sim_elapsed'] = now - stats['sim_start']


def _finish_run():
    """Save completed run stats and stop threads."""
    global completed_fixed, completed_ai, sim_running
    import copy
    saved = copy.deepcopy(stats)
    saved['mode'] = sim_mode
    saved['timeseries'] = list(timeseries_log)
    if sim_mode == MODE_FIXED:
        completed_fixed = saved
    elif sim_mode == MODE_AI:
        completed_ai = saved
    stop_threads()
    sim_running = False


# ─────────────────────────────────────────────
#  CSV Export
# ─────────────────────────────────────────────
def _ensure_results_dir():
    os.makedirs("results", exist_ok=True)


def _avg_wait(s):
    if s['wait_samples'] > 0:
        return round(s['total_wait'] / s['wait_samples'], 2)
    return 0.0


def _avg_queue(s):
    if s['queue_obs'] > 0:
        return round(s['queue_sum'] / s['queue_obs'], 2)
    return 0.0


def _throughput(s):
    elapsed_min = s['sim_elapsed'] / 60.0
    if elapsed_min > 0:
        return round(s['served'] / elapsed_min, 2)
    return 0.0


def export_summary_csv():
    """Export summary stats for both modes to results/summary_<timestamp>.csv"""
    _ensure_results_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"results/summary_{ts}.csv"
    rows = []
    for s in [completed_fixed, completed_ai]:
        if s is None:
            continue
        rows.append({
            'mode':            s.get('mode', '?'),
            'scenario_seed':   SCENARIO_SEED,
            'sim_duration_s':  round(s.get('sim_elapsed', 0), 1),
            'total_generated': s['generated'],
            'total_served':    s['served'],
            'avg_wait_s':      _avg_wait(s),
            'max_wait_s':      round(s['max_wait'], 2),
            'avg_queue':       _avg_queue(s),
            'max_queue':       s['max_queue'],
            'throughput_vpm':  _throughput(s),
            'timestamp':       ts,
        })
    if not rows:
        return None
    try:
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        print(f"CSV export error: {e}")
        return None
    return filename


def export_timeseries_csv():
    """Export time-series queue data to results/timeseries_<timestamp>.csv"""
    _ensure_results_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"results/timeseries_{ts}.csv"
    all_rows = []
    for s in [completed_fixed, completed_ai]:
        if s is None:
            continue
        for row in s.get('timeseries', []):
            r = dict(row)
            r['mode'] = s.get('mode', '?')
            all_rows.append(r)
    if not all_rows:
        return None
    try:
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)
    except Exception as e:
        print(f"Timeseries CSV export error: {e}")
        return None
    return filename


# ─────────────────────────────────────────────
#  Drawing helpers
# ─────────────────────────────────────────────
def draw_panel(surf, x, y, w, h, alpha=210):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill((8, 12, 35, alpha))
    surf.blit(s, (x, y))


def draw_bar(surf, x, y, w, h, fraction, color, bg=(30, 30, 55)):
    pygame.draw.rect(surf, bg, (x, y, w, h))
    filled = int(w * max(0.0, min(1.0, fraction)))
    if filled > 0:
        pygame.draw.rect(surf, color, (x, y, filled, h))
    pygame.draw.rect(surf, (80, 80, 110), (x, y, w, h), 1)


def pct_improve(base, new):
    """Return improvement percentage (positive = improvement)."""
    if base is None or new is None:
        return None
    if base == 0:
        return None
    return ((base - new) / base) * 100.0


# ─────────────────────────────────────────────
#  Main application
# ─────────────────────────────────────────────
def main():
    global sim_mode, sim_paused, sim_running
    global currentGreen, currentYellow, nextGreen

    # Build allowed vehicle list
    global allowedVehicleTypesList
    i = 0
    for vehicleType in allowedVehicleTypes:
        if allowedVehicleTypes[vehicleType]:
            allowedVehicleTypesList.append(i)
        i += 1

    # Pre-generate scenario
    _generate_scenario()

    # Pygame setup
    screenWidth  = 1400
    screenHeight = 800
    screen       = pygame.display.set_mode((screenWidth, screenHeight))
    pygame.display.set_caption("AI Traffic Management System")

    background    = pygame.image.load('images/intersection.png')
    redSignal     = pygame.image.load('images/signals/red.png')
    yellowSignal  = pygame.image.load('images/signals/yellow.png')
    greenSignal   = pygame.image.load('images/signals/green.png')

    # Fonts
    font_large  = pygame.font.SysFont("consolas", 20, bold=True)
    font_small  = pygame.font.SysFont("consolas", 15)
    font_title  = pygame.font.SysFont("consolas", 18, bold=True)
    font_count  = pygame.font.SysFont("consolas", 16, bold=True)
    font_tiny   = pygame.font.SysFont("consolas", 11, bold=True)
    font_h1     = pygame.font.SysFont("consolas", 28, bold=True)
    font_h2     = pygame.font.SysFont("consolas", 22, bold=True)
    font_btn    = pygame.font.SysFont("consolas", 17, bold=True)

    # Colors
    BLACK       = (0,   0,   0)
    WHITE       = (255, 255, 255)
    YELLOW_COL  = (255, 200,   0)
    GREEN_COL   = ( 50, 220,  80)
    RED_COL     = (220,  50,  50)
    ACCENT      = ( 80, 160, 255)
    DIM         = (140, 140, 160)
    AMBER       = (255, 165,   0)
    DARK_BG     = ( 12,  14,  30)
    PANEL_BG    = ( 18,  22,  48)
    AI_COL      = ( 50, 220,  80)   # green for AI
    FX_COL      = (255, 165,   0)   # amber for fixed-time
    DANGER      = (220,  50,  50)
    TEAL        = ( 50, 200, 200)

    # Parked vehicles
    _parked_img_cache = {}
    for _px, _py, _pdir, _pvtype in PARKED_VEHICLES:
        _key = (_pdir, _pvtype)
        if _key not in _parked_img_cache:
            try:
                _parked_img_cache[_key] = pygame.image.load(
                    f'images/{_pdir}/{_pvtype}.png').convert_alpha()
            except Exception:
                _parked_img_cache[_key] = None

    dir_labels     = ['RIGHT', 'DOWN', 'LEFT', 'UP']
    countBadgePos  = [(530, 250), (810, 250), (810, 590), (530, 590)]

    clock           = pygame.time.Clock()
    export_msg      = ""
    export_msg_timer = 0

    # ── Button helper ─────────────────────────────────────────────────────────
    class Button:
        def __init__(self, x, y, w, h, text, color, hover_color, text_color=WHITE):
            self.rect        = pygame.Rect(x, y, w, h)
            self.text        = text
            self.color       = color
            self.hover_color = hover_color
            self.text_color  = text_color
            self.hovered     = False

        def draw(self, surf, font):
            col = self.hover_color if self.hovered else self.color
            pygame.draw.rect(surf, col, self.rect, border_radius=6)
            pygame.draw.rect(surf, WHITE, self.rect, 1, border_radius=6)
            lbl = font.render(self.text, True, self.text_color)
            lr  = lbl.get_rect(center=self.rect.center)
            surf.blit(lbl, lr)

        def check(self, pos):
            self.hovered = self.rect.collidepoint(pos)
            return self.hovered

        def clicked(self, pos):
            return self.rect.collidepoint(pos)

    # Menu buttons
    bw, bh = 260, 46
    cx = screenWidth // 2
    btn_fixed    = Button(cx - bw//2, 260, bw, bh, "Fixed-Time Mode",    (100, 60,  0),  (180, 110,  0), AMBER)
    btn_ai       = Button(cx - bw//2, 320, bw, bh, "AI Adaptive Mode",   ( 0, 80,  30),  (  0, 140, 60), GREEN_COL)
    btn_start    = Button(cx - bw//2, 400, bw, bh, "Start Simulation",   (30,  60, 160), (60, 100, 220))
    btn_analytics= Button(cx - bw//2, 460, bw, bh, "View Analytics",     (50,  50,  90), (80,  80, 140))
    btn_results  = Button(cx - bw//2, 520, bw, bh, "Comparison Results", (70,  20,  70), (110, 40, 110))

    # Sim-screen buttons (bottom strip)
    btn_pause    = Button(10,  760, 130, 34, "Pause",         (40, 40, 80),   (70, 70, 120))
    btn_reset    = Button(150, 760, 130, 34, "Reset",         (80, 20, 20),   (130, 40, 40))
    btn_mode_fx  = Button(290, 760, 180, 34, "Fixed-Time (1)", (100, 60,  0),  (160, 100,  0), AMBER)
    btn_mode_ai  = Button(480, 760, 180, 34, "AI Adaptive (2)",(  0, 80,  30), (  0, 130, 60), GREEN_COL)
    btn_view_an  = Button(670, 760, 150, 34, "Analytics (A)",  (50, 50,  90),  (80,  80, 140))
    btn_view_res = Button(830, 760, 170, 34, "Results",        (70, 20,  70),  (110, 40, 110))
    btn_export   = Button(1010,760, 160, 34, "Export CSV",     (20, 70,  70),  ( 40, 110, 110))
    btn_back     = Button(1180,760, 120, 34, "Back (Esc)",     (50, 50,  50),  ( 80,  80,  80))

    # Analytics / Results back button
    btn_dash_back = Button(10, 760, 130, 34, "Back (Esc)", (50, 50, 50), (80, 80, 80))

    # Selected mode on menu screen
    selected_mode = MODE_AI   # default selection

    def _draw_menu():
        screen.fill(DARK_BG)
        # Gradient header strip
        hdr = pygame.Surface((screenWidth, 120), pygame.SRCALPHA)
        for row in range(120):
            alpha = int(255 * (1 - row / 120))
            pygame.draw.line(hdr, (*ACCENT[:3], alpha), (0, row), (screenWidth, row))
        screen.blit(hdr, (0, 0))

        title = font_h1.render("AI-Based Adaptive Traffic Management System", True, WHITE)
        screen.blit(title, title.get_rect(center=(cx, 40)))
        sub   = font_h2.render("Fixed-Time vs AI Adaptive Comparison", True, ACCENT)
        screen.blit(sub,   sub.get_rect(center=(cx, 80)))

        # Mode selection indicator
        mode_lbl = font_title.render("Select Controller Mode:", True, DIM)
        screen.blit(mode_lbl, mode_lbl.get_rect(center=(cx, 220)))

        btn_fixed.draw(screen, font_btn)
        btn_ai.draw(screen, font_btn)

        # Highlight selected
        sel_rect = btn_fixed.rect if selected_mode == MODE_FIXED else btn_ai.rect
        pygame.draw.rect(screen, WHITE, sel_rect, 3, border_radius=6)

        btn_start.draw(screen, font_btn)
        btn_analytics.draw(screen, font_btn)
        btn_results.draw(screen, font_btn)

        # Status of completed runs
        y_info = 590
        def _run_tag(s, col, label):
            nonlocal y_info
            if s is not None:
                aw  = _avg_wait(s)
                aq  = _avg_queue(s)
                thr = _throughput(s)
                msg = (f"{label}: gen={s['generated']}  served={s['served']}"
                       f"  avg_wait={aw:.1f}s  avg_q={aq:.1f}  thr={thr:.1f}vpm")
                lbl = font_small.render(msg, True, col)
                screen.blit(lbl, lbl.get_rect(center=(cx, y_info)))
                y_info += 22
        _run_tag(completed_fixed, AMBER,    "FIXED ")
        _run_tag(completed_ai,    GREEN_COL, "AI    ")

        info = font_tiny.render(
            f"Scenario seed: {SCENARIO_SEED}   Duration: {SIM_DURATION}s per run   "
            f"[SPACE] Pause  [R] Reset  [1] Fixed  [2] AI  [A] Analytics  [Esc] Back",
            True, DIM)
        screen.blit(info, info.get_rect(center=(cx, 770)))

    def _draw_sim_screen():
        nonlocal export_msg, export_msg_timer
        screen.blit(background, (0, 0))

        # No-parking zones
        for zone_rect, _ in NO_PARKING_ZONES:
            pygame.draw.rect(screen, YELLOW_COL, zone_rect, 3)
            for off in range(0, zone_rect.w + zone_rect.h, 10):
                x1 = zone_rect.x + off
                x2 = zone_rect.x + off - zone_rect.h
                x1c = max(zone_rect.x, min(zone_rect.x + zone_rect.w, x1))
                x2c = max(zone_rect.x, min(zone_rect.x + zone_rect.w, x2))
                if x1c != x2c:
                    pygame.draw.line(screen, (200, 155, 0),
                                     (x1c, zone_rect.y + 2),
                                     (x2c, zone_rect.y + zone_rect.h - 2), 1)
            np_lbl = font_tiny.render("NO P", True, (255, 220, 0))
            screen.blit(np_lbl, (zone_rect.x + 4, zone_rect.y + zone_rect.h // 2 - 6))

        # Parked vehicles
        for px, py, pdir, pvtype in PARKED_VEHICLES:
            img = _parked_img_cache.get((pdir, pvtype))
            if img:
                screen.blit(img, (px, py))

        # Signals
        if signals:
            for i in range(noOfSignals):
                if i == currentGreen:
                    if currentYellow == 1:
                        signals[i].signalText = signals[i].yellow
                        screen.blit(yellowSignal, signalCoods[i])
                    else:
                        signals[i].signalText = signals[i].green
                        screen.blit(greenSignal, signalCoods[i])
                else:
                    signals[i].signalText = "---"
                    screen.blit(redSignal, signalCoods[i])

            for i in range(noOfSignals):
                txt = font_large.render(str(signals[i].signalText), True, WHITE, BLACK)
                screen.blit(txt, signalTimerCoods[i])

        # Vehicle count badges
        for i in range(noOfSignals):
            count   = ai_vehicle_counts[i]
            bx, by  = countBadgePos[i]
            badge   = pygame.Surface((90, 22), pygame.SRCALPHA)
            badge.fill((0, 0, 0, 160))
            screen.blit(badge, (bx - 5, by - 3))
            if i == currentGreen:    col = GREEN_COL
            elif i == ai_next_choice: col = YELLOW_COL
            else:                    col = (200, 200, 200)
            lbl = font_count.render(f"{dir_labels[i]}: {count}", True, col)
            screen.blit(lbl, (bx, by))

        # ── Left panel: Controller status ──────────────────────────────
        panel_x, panel_y = 8, 8
        panel_w, panel_h = 318, 220
        draw_panel(screen, panel_x, panel_y, panel_w, panel_h)

        mode_col  = AI_COL if sim_mode == MODE_AI else FX_COL
        mode_name = "AI ADAPTIVE" if sim_mode == MODE_AI else "FIXED-TIME"
        title_txt = font_title.render(f"● {mode_name} MODE", True, mode_col)
        screen.blit(title_txt, (panel_x + 8, panel_y + 8))

        pygame.draw.line(screen, ACCENT,
                         (panel_x + 8, panel_y + 28),
                         (panel_x + panel_w - 8, panel_y + 28), 1)

        if currentYellow == 1:
            phase_col  = YELLOW_COL
            phase_text = f"YELLOW  ({directionNumbers[currentGreen].upper()})"
        else:
            phase_col  = GREEN_COL
            phase_text = f"GREEN   ({directionNumbers[currentGreen].upper()})"
        screen.blit(font_small.render(phase_text, True, phase_col), (panel_x + 8, panel_y + 34))

        # Direction rows
        count_y = panel_y + 54
        for i in range(noOfSignals):
            cnt    = ai_vehicle_counts[i]
            gt     = ai_green_times[i] if sim_mode == MODE_AI else FIXED_GREEN
            wc     = wait_cycles[i]
            dname  = directionNumbers[i].upper().ljust(6)
            bar_len = min(int(cnt * 4), 80)
            if i == currentGreen:    c = GREEN_COL
            elif i == ai_next_choice: c = YELLOW_COL
            elif wc >= MAX_WAIT_CYCLES: c = DANGER
            elif wc >= MAX_WAIT_CYCLES - 1: c = (255, 165, 0)
            else: c = DIM
            wc_str = f" W{wc}" if wc > 0 else "   "
            line_txt = font_small.render(f"  {dname} {cnt:2d} veh {gt:2d}s{wc_str}", True, c)
            screen.blit(line_txt, (panel_x + 8, count_y))
            pygame.draw.rect(screen, (30, 30, 50), (panel_x + 195, count_y + 3, 80, 8))
            pygame.draw.rect(screen, c, (panel_x + 195, count_y + 3, bar_len, 8))
            count_y += 20

        # AI log
        pygame.draw.line(screen, (60, 60, 90),
                         (panel_x + 8, count_y + 2),
                         (panel_x + panel_w - 8, count_y + 2), 1)
        if ai_log:
            last = ai_log[-1]
            log_surf = font_small.render(last, True, (180, 220, 255))
            screen.blit(log_surf, (panel_x + 8, count_y + 6))

        # ── Right panel: Live analytics ────────────────────────────────
        rp_x, rp_y = screenWidth - 328, 8
        rp_w, rp_h = 320, 240
        draw_panel(screen, rp_x, rp_y, rp_w, rp_h)
        screen.blit(font_title.render("LIVE ANALYTICS", True, TEAL),
                    (rp_x + 8, rp_y + 8))
        pygame.draw.line(screen, TEAL,
                         (rp_x + 8, rp_y + 28), (rp_x + rp_w - 8, rp_y + 28), 1)

        aw     = _avg_wait(stats)
        aq     = _avg_queue(stats)
        thr    = _throughput(stats)
        waiting_now = sum(ai_vehicle_counts)
        elapsed_s   = int(stats.get('sim_elapsed', 0))

        metrics = [
            ("Elapsed",     f"{elapsed_s}s / {SIM_DURATION}s"),
            ("Generated",   str(stats['generated'])),
            ("Served",      str(stats['served'])),
            ("Waiting Now", str(waiting_now)),
            ("Avg Wait",    f"{aw:.1f}s"),
            ("Max Wait",    f"{stats['max_wait']:.1f}s"),
            ("Avg Queue",   f"{aq:.1f}"),
            ("Max Queue",   str(stats['max_queue'])),
            ("Throughput",  f"{thr:.1f} vpm"),
        ]
        my = rp_y + 34
        for label, val in metrics:
            lbl_s  = font_small.render(label + ":", True, DIM)
            val_s  = font_small.render(val, True, WHITE)
            screen.blit(lbl_s, (rp_x + 8, my))
            screen.blit(val_s, (rp_x + rp_w - val_s.get_width() - 8, my))
            my += 20

        # Timer progress bar
        frac = min(1.0, elapsed_s / SIM_DURATION) if SIM_DURATION > 0 else 0
        draw_bar(screen, rp_x + 8, my + 2, rp_w - 16, 10, frac, mode_col)
        if frac >= 1.0:
            screen.blit(font_tiny.render("Run complete!", True, GREEN_COL), (rp_x + 8, my + 14))

        # Pause overlay
        if sim_paused:
            ov = pygame.Surface((screenWidth, screenHeight), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 80))
            screen.blit(ov, (0, 0))
            pause_lbl = font_h2.render("⏸  PAUSED  ⏸", True, YELLOW_COL)
            screen.blit(pause_lbl, pause_lbl.get_rect(center=(screenWidth // 2, screenHeight // 2)))

        # Bottom button strip
        btn_pause.text = "Resume" if sim_paused else "Pause"
        for btn in [btn_pause, btn_reset, btn_mode_fx, btn_mode_ai,
                    btn_view_an, btn_view_res, btn_export, btn_back]:
            btn.draw(screen, font_small)

        # Export message
        if export_msg_timer > 0:
            msg_s = font_small.render(export_msg, True, GREEN_COL)
            screen.blit(msg_s, (10, 740))
            export_msg_timer -= 1

        # Vehicles
        for vehicle in simulation:
            screen.blit(vehicle.image, [vehicle.x, vehicle.y])
            vehicle.move()

    def _draw_analytics():
        """Full-screen analytics dashboard."""
        screen.fill(DARK_BG)
        screen.blit(font_h2.render("Real-Time Traffic Analytics Dashboard", True, TEAL),
                    (screenWidth // 2 - 300, 12))
        pygame.draw.line(screen, TEAL, (10, 42), (screenWidth - 10, 42), 1)

        y_cur = 52

        # ── Direction-wise table ───────────────────────────────────────
        cols = ["Direction", "Waiting", "Signal", "Queue", "Avg Wait"]
        col_x = [20, 150, 260, 380, 490]
        # Header
        for ci, ch in enumerate(cols):
            screen.blit(font_title.render(ch, True, ACCENT), (col_x[ci], y_cur))
        y_cur += 24
        pygame.draw.line(screen, ACCENT, (10, y_cur), (650, y_cur), 1)
        y_cur += 4

        for di, d in enumerate(['right', 'down', 'left', 'up']):
            waiting = ai_vehicle_counts[di]
            q       = stats['dir_queue'][di]
            dw_cnt  = stats['dir_wait_cnt'][di]
            dw_sum  = stats['dir_wait_sum'][di]
            daw     = round(dw_sum / dw_cnt, 1) if dw_cnt > 0 else 0.0
            if di == currentGreen:
                sig_txt = "GREEN" if currentYellow == 0 else "YELLOW"
                sig_col = GREEN_COL if currentYellow == 0 else YELLOW_COL
            else:
                sig_txt = "RED"
                sig_col = RED_COL

            row_vals = [d.upper(), str(waiting), sig_txt, str(q), f"{daw:.1f}s"]
            row_cols = [WHITE, WHITE, sig_col, WHITE, WHITE]
            for ci in range(len(cols)):
                screen.blit(font_small.render(row_vals[ci], True, row_cols[ci]), (col_x[ci], y_cur))

            # Congestion bar
            draw_bar(screen, col_x[-1] + 70, y_cur + 3, 140, 12, min(1.0, waiting / 20),
                     DANGER if waiting > 10 else AMBER if waiting > 5 else GREEN_COL)
            y_cur += 22

        y_cur += 10
        pygame.draw.line(screen, (60, 60, 90), (10, y_cur), (screenWidth - 10, y_cur), 1)
        y_cur += 10

        # ── Live summary ───────────────────────────────────────────────
        aw  = _avg_wait(stats)
        aq  = _avg_queue(stats)
        thr = _throughput(stats)
        summary_items = [
            ("Mode",        "AI Adaptive" if sim_mode == MODE_AI else "Fixed-Time"),
            ("Elapsed",     f"{int(stats.get('sim_elapsed', 0))}s"),
            ("Generated",   str(stats['generated'])),
            ("Served",      str(stats['served'])),
            ("Waiting Now", str(sum(ai_vehicle_counts))),
            ("Avg Wait",    f"{aw:.2f}s"),
            ("Max Wait",    f"{stats['max_wait']:.2f}s"),
            ("Avg Queue",   f"{aq:.2f}"),
            ("Max Queue",   str(stats['max_queue'])),
            ("Throughput",  f"{thr:.1f} vpm"),
        ]
        cols_n = 5
        item_w = (screenWidth - 40) // cols_n
        si = 0
        for label, val in summary_items:
            xi = 20 + (si % cols_n) * item_w
            yi = y_cur + (si // cols_n) * 50
            draw_panel(screen, xi, yi, item_w - 10, 44, 200)
            screen.blit(font_tiny.render(label, True, DIM),  (xi + 6, yi + 4))
            screen.blit(font_title.render(val,  True, WHITE), (xi + 6, yi + 20))
            si += 1
        y_cur += (((len(summary_items) - 1) // cols_n) + 1) * 50 + 14

        pygame.draw.line(screen, (60, 60, 90), (10, y_cur), (screenWidth - 10, y_cur), 1)
        y_cur += 10

        # ── Performance Charts (Fixed vs AI) ──────────────────────────
        chart_title = font_title.render("Fixed-Time (amber) vs AI Adaptive (green) — Completed Runs", True, DIM)
        screen.blit(chart_title, (20, y_cur))
        y_cur += 24

        metrics_chart = [
            ("Avg Wait (s)",    lambda s: _avg_wait(s),    40.0),
            ("Served",          lambda s: float(s['served']), 200.0),
            ("Avg Queue",       lambda s: _avg_queue(s),   20.0),
            ("Throughput(vpm)", lambda s: _throughput(s),  100.0),
        ]
        cw, ch_h = 280, 90
        chart_y  = y_cur
        for ci, (label, fn, max_val) in enumerate(metrics_chart):
            cx_c = 20 + ci * (cw + 20)
            # Panel
            draw_panel(screen, cx_c, chart_y, cw, ch_h + 30, 180)
            screen.blit(font_tiny.render(label, True, ACCENT), (cx_c + 6, chart_y + 4))
            # Bars
            bar_w = 70
            for ki, (s_data, col, lbl_txt) in enumerate(
                    [(completed_fixed, FX_COL, "FX"), (completed_ai, AI_COL, "AI")]):
                bx = cx_c + 20 + ki * (bar_w + 30)
                by = chart_y + ch_h + 10
                if s_data is not None:
                    val = fn(s_data)
                    frac = min(1.0, val / max_val) if max_val > 0 else 0
                    bar_px = int(ch_h * frac)
                    pygame.draw.rect(screen, (30, 30, 55),
                                     (bx, chart_y + 20, bar_w, ch_h - 10))
                    pygame.draw.rect(screen, col,
                                     (bx, chart_y + 20 + (ch_h - 10) - bar_px, bar_w, bar_px))
                    pygame.draw.rect(screen, WHITE,
                                     (bx, chart_y + 20, bar_w, ch_h - 10), 1)
                    val_txt = font_tiny.render(f"{val:.1f}", True, WHITE)
                    screen.blit(val_txt, (bx + bar_w // 2 - val_txt.get_width() // 2,
                                          chart_y + 20 + (ch_h - 10) - bar_px - 14))
                else:
                    pygame.draw.rect(screen, (40, 40, 60),
                                     (bx, chart_y + 20, bar_w, ch_h - 10))
                    screen.blit(font_tiny.render("N/A", True, DIM),
                                (bx + 20, chart_y + 20 + (ch_h - 10) // 2))
                screen.blit(font_tiny.render(lbl_txt, True, col), (bx + bar_w // 2 - 8, by + 2))

        btn_dash_back.draw(screen, font_small)

    def _draw_results():
        """Final comparison results screen."""
        screen.fill(DARK_BG)
        screen.blit(font_h2.render("Fixed-Time vs AI Adaptive — Final Comparison", True, WHITE),
                    (screenWidth // 2 - 340, 12))
        pygame.draw.line(screen, ACCENT, (10, 44), (screenWidth - 10, 44), 1)

        if completed_fixed is None and completed_ai is None:
            screen.blit(font_h2.render("No completed runs yet. Run both modes first.",
                                       True, DANGER), (100, 200))
            btn_dash_back.draw(screen, font_small)
            return

        headers = ["Metric", "Fixed-Time", "AI Adaptive", "Improvement"]
        col_x   = [20, 320, 560, 800]
        y_r     = 56

        for ci, h in enumerate(headers):
            col = FX_COL if ci == 1 else AI_COL if ci == 2 else ACCENT if ci == 3 else WHITE
            screen.blit(font_title.render(h, True, col), (col_x[ci], y_r))
        y_r += 26
        pygame.draw.line(screen, ACCENT, (10, y_r), (1100, y_r), 1)
        y_r += 6

        def fv(s, fn):
            return fn(s) if s is not None else None

        rows = [
            ("Generated",       lambda s: s['generated'],        lambda v: str(v)),
            ("Served",          lambda s: s['served'],           lambda v: str(v)),
            ("Avg Wait (s)",    _avg_wait,                       lambda v: f"{v:.2f}"),
            ("Max Wait (s)",    lambda s: s['max_wait'],         lambda v: f"{v:.2f}"),
            ("Avg Queue",       _avg_queue,                      lambda v: f"{v:.2f}"),
            ("Max Queue",       lambda s: s['max_queue'],        lambda v: str(v)),
            ("Throughput(vpm)", _throughput,                     lambda v: f"{v:.2f}"),
        ]
        # Metrics where lower is better → improvement = reduction
        lower_is_better = {"Avg Wait (s)", "Max Wait (s)", "Avg Queue", "Max Queue"}

        for metric_name, fn, fmt in rows:
            fx_val = fv(completed_fixed, fn)
            ai_val = fv(completed_ai,   fn)
            fx_str = fmt(fx_val) if fx_val is not None else "—"
            ai_str = fmt(ai_val) if ai_val is not None else "—"

            # Improvement
            imp_str = "N/A"
            imp_col = DIM
            if fx_val is not None and ai_val is not None:
                if metric_name in lower_is_better:
                    pct = pct_improve(fx_val, ai_val)
                else:
                    # Higher is better: improvement if AI > fixed
                    if fx_val != 0:
                        pct = ((ai_val - fx_val) / abs(fx_val)) * 100.0
                    else:
                        pct = None
                if pct is not None:
                    imp_str = f"{pct:+.1f}%"
                    imp_col = GREEN_COL if pct > 0 else DANGER if pct < 0 else DIM

            row_data = [metric_name, fx_str, ai_str, imp_str]
            row_cols = [WHITE, FX_COL, AI_COL, imp_col]
            for ci, (val_s, rc) in enumerate(zip(row_data, row_cols)):
                screen.blit(font_small.render(val_s, True, rc), (col_x[ci], y_r))
            y_r += 28

        pygame.draw.line(screen, (60, 60, 90), (10, y_r + 4), (1100, y_r + 4), 1)
        y_r += 16

        # Scenario info
        info_txt = (f"Scenario Seed: {SCENARIO_SEED}   "
                    f"Duration: {SIM_DURATION}s per run   "
                    f"Fixed Green: {FIXED_GREEN}s   "
                    f"AI Min/Max: {MIN_GREEN}/{MAX_GREEN}s")
        screen.blit(font_small.render(info_txt, True, DIM), (20, y_r))

        # Note about improvement direction
        note = ("Improvement: positive = AI is better.  "
                "For wait/queue metrics: AI wait < Fixed wait → positive.")
        screen.blit(font_tiny.render(note, True, DIM), (20, y_r + 20))

        btn_dash_back.draw(screen, font_small)
        # Export button on results screen
        bexp = Button(200, 760, 200, 34, "Export CSV", (20, 70, 70), (40, 110, 110))
        bexp.draw(screen, font_small)

    # ── Main loop ─────────────────────────────────────────────────────────────
    _active_sim_mode = None   # tracks the last launched MODE_AI or MODE_FIXED
    while True:
        mouse_pos = pygame.mouse.get_pos()
        dt        = clock.tick(60)

        # Sample queues (only during active run)
        if sim_running and not sim_paused:
            _sample_queues()

        # Auto-finish run when duration expires
        if sim_running and stats['sim_start'] is not None:
            elapsed = time.time() - stats['sim_start']
            if elapsed >= SIM_DURATION:
                _finish_run()

        # ── Events ────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                stop_threads()
                pygame.quit()
                sys.exit()

            # ── Keyboard shortcuts ────────────────────────────────────
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if sim_mode in (MODE_ANALYTICS, MODE_RESULTS):
                        if sim_running and _active_sim_mode:
                            sim_mode = _active_sim_mode
                        else:
                            sim_mode = MODE_MENU
                    elif sim_mode in (MODE_AI, MODE_FIXED):
                        reset_to_menu()
                    else:
                        stop_threads()
                        pygame.quit()
                        sys.exit()

                elif event.key == pygame.K_SPACE:
                    if sim_mode in (MODE_AI, MODE_FIXED):
                        sim_paused = not sim_paused

                elif event.key == pygame.K_r:
                    if sim_mode in (MODE_AI, MODE_FIXED):
                        reset_to_menu()

                elif event.key == pygame.K_1:
                    if currentYellow == 0:
                        selected_mode = MODE_FIXED
                        if sim_mode in (MODE_AI, MODE_FIXED):
                            _active_sim_mode = MODE_FIXED
                            start_run(MODE_FIXED)
                        else:
                            selected_mode = MODE_FIXED

                elif event.key == pygame.K_2:
                    if currentYellow == 0:
                        selected_mode = MODE_AI
                        if sim_mode in (MODE_AI, MODE_FIXED):
                            _active_sim_mode = MODE_AI
                            start_run(MODE_AI)
                        else:
                            selected_mode = MODE_AI

                elif event.key == pygame.K_a:
                    if sim_mode not in (MODE_MENU,):
                        sim_mode = MODE_ANALYTICS

            # ── Mouse clicks ──────────────────────────────────────────
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos

                if sim_mode == MODE_MENU:
                    if btn_fixed.clicked(pos):
                        selected_mode = MODE_FIXED
                    elif btn_ai.clicked(pos):
                        selected_mode = MODE_AI
                    elif btn_start.clicked(pos):
                        _active_sim_mode = selected_mode
                        start_run(selected_mode)
                    elif btn_analytics.clicked(pos):
                        sim_mode = MODE_ANALYTICS
                    elif btn_results.clicked(pos):
                        sim_mode = MODE_RESULTS

                elif sim_mode in (MODE_AI, MODE_FIXED):
                    if btn_pause.clicked(pos):
                        sim_paused = not sim_paused
                    elif btn_reset.clicked(pos):
                        _active_sim_mode = None
                        reset_to_menu()
                    elif btn_mode_fx.clicked(pos) and currentYellow == 0:
                        _active_sim_mode = MODE_FIXED
                        start_run(MODE_FIXED)
                    elif btn_mode_ai.clicked(pos) and currentYellow == 0:
                        _active_sim_mode = MODE_AI
                        start_run(MODE_AI)
                    elif btn_view_an.clicked(pos):
                        sim_mode = MODE_ANALYTICS
                    elif btn_view_res.clicked(pos):
                        sim_mode = MODE_RESULTS
                    elif btn_back.clicked(pos):
                        reset_to_menu()
                    elif btn_export.clicked(pos):
                        f1 = export_summary_csv()
                        f2 = export_timeseries_csv()
                        if f1:
                            export_msg   = f"Saved: {os.path.basename(f1)}"
                            export_msg_timer = 180
                        else:
                            export_msg   = "No data to export yet."
                            export_msg_timer = 120

                elif sim_mode in (MODE_ANALYTICS, MODE_RESULTS):
                    if btn_dash_back.clicked(pos):
                        if sim_running and _active_sim_mode:
                            sim_mode = _active_sim_mode
                        else:
                            sim_mode = MODE_MENU
                    # Export button on results screen
                    exp_rect = pygame.Rect(200, 760, 200, 34)
                    if exp_rect.collidepoint(pos):
                        f1 = export_summary_csv()
                        f2 = export_timeseries_csv()
                        if f1:
                            export_msg   = f"Saved: {os.path.basename(f1)}"
                            export_msg_timer = 180

        # ── Hover updates ─────────────────────────────────────────────
        if sim_mode == MODE_MENU:
            for btn in [btn_fixed, btn_ai, btn_start, btn_analytics, btn_results]:
                btn.check(mouse_pos)
        elif sim_mode in (MODE_AI, MODE_FIXED):
            for btn in [btn_pause, btn_reset, btn_mode_fx, btn_mode_ai,
                        btn_view_an, btn_view_res, btn_export, btn_back]:
                btn.check(mouse_pos)
        elif sim_mode in (MODE_ANALYTICS, MODE_RESULTS):
            btn_dash_back.check(mouse_pos)

        # ── Render ────────────────────────────────────────────────────
        if sim_mode == MODE_MENU:
            _draw_menu()
        elif sim_mode in (MODE_AI, MODE_FIXED):
            _draw_sim_screen()
        elif sim_mode == MODE_ANALYTICS:
            _draw_analytics()
        elif sim_mode == MODE_RESULTS:
            _draw_results()

        pygame.display.update()


if __name__ == "__main__":
    main()
