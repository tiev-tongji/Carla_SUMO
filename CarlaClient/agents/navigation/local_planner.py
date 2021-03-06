#!/usr/bin/env python

# Copyright (c) 2018 Intel Labs.
# authors: German Ros (german.ros@intel.com)
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

""" This module contains a local planner to perform low-level waypoint following based on PID controllers. """

from enum import Enum
from collections import deque
import time
import random

import carla
from agents.navigation.controller import VehiclePIDController
from agents.tools.misc import distance_vehicle, draw_waypoints

class RoadOption(Enum):
    """
    RoadOption represents the possible topological configurations when moving from a segment of lane to other.
    """
    VOID = -1
    LEFT = 1
    RIGHT = 2
    STRAIGHT = 3
    LANEFOLLOW = 4
    CHANGELANELEFT = 5
    CHANGELANERIGHT = 6


class LocalPlanner(object):
    """
    LocalPlanner implements the basic behavior of following a trajectory of waypoints that is generated on-the-fly.
    The low-level motion of the vehicle is computed by using two PID controllers, one is used for the lateral control
    and the other for the longitudinal control (cruise speed).

    When multiple paths are available (intersections) this local planner makes a random choice.
    """

    # minimum distance to target waypoint as a percentage (e.g. within 90% of
    # total distance)
    MIN_DISTANCE_PERCENTAGE = 0.9

    def __init__(self, vehicle, opt_dict={}):
        """
        :param vehicle: actor to apply to local planner logic onto
        :param opt_dict: dictionary of arguments with the following semantics:
            dt -- time difference between physics control in seconds. This is typically fixed from server side
                  using the arguments -benchmark -fps=F . In this case dt = 1/F

            target_speed -- desired cruise speed in Km/h

            sampling_radius -- search radius for next waypoints in seconds: e.g. 0.5 seconds ahead

            lateral_control_dict -- dictionary of arguments to setup the lateral PID controller
                                    {'K_P':, 'K_D':, 'K_I':, 'dt'}

            longitudinal_control_dict -- dictionary of arguments to setup the longitudinal PID controller
                                        {'K_P':, 'K_D':, 'K_I':, 'dt'}
        """
        self._vehicle = vehicle
        self._map = self._vehicle.get_world().get_map()

        self._dt = None
        self._target_speed = None
        self._sampling_radius = None
        self._min_distance = None
        self._current_waypoint = None
        self._target_road_option = None
        self._next_waypoints = None
        self._target_waypoint = None
        self._vehicle_controller = None
        self._global_plan = None
        # queue with tuples of (waypoint, RoadOption)
        self._waypoints_queue = deque(maxlen=600)
        self._buffer_size = 5
        self.message_waypoints = 3
        # 当前阶段完成的waypoints个数
        self.finished_waypoints = 0
        self._waypoint_buffer = deque(maxlen=self._buffer_size)

        # initializing controller
        self.init_controller(opt_dict)

    def __del__(self):
        if self._vehicle:
            self._vehicle.destroy()
        print("Destroying ego-vehicle!")

    def init_controller(self, opt_dict):
        """
        Controller initialization.

        :param opt_dict: dictionary of arguments.
        :return:
        """
        # default params
        self._dt = 1.0 / 20.0
        self._target_speed = 20.0  # Km/h
        self._sampling_radius = self._target_speed * 0.5 / 3.6  # 0.5 seconds horizon
        self._min_distance = self._sampling_radius * self.MIN_DISTANCE_PERCENTAGE
        args_lateral_dict = {
            'K_P': 1.95,
            'K_D': 0.01,
            'K_I': 1.4,
            'dt': self._dt}
        args_longitudinal_dict = {
            'K_P': 1.0,
            'K_D': 0,
            'K_I': 1,
            'dt': self._dt}

        # parameters overload
        if 'dt' in opt_dict:
            self._dt = opt_dict['dt']
        if 'target_speed' in opt_dict:
            self._target_speed = opt_dict['target_speed']
        if 'sampling_radius' in opt_dict:
            self._sampling_radius = self._target_speed * \
                opt_dict['sampling_radius'] / 3.6
        if 'lateral_control_dict' in opt_dict:
            args_lateral_dict = opt_dict['lateral_control_dict']
        if 'longitudinal_control_dict' in opt_dict:
            args_longitudinal_dict = opt_dict['longitudinal_control_dict']

        self._current_waypoint = self._map.get_waypoint(
            self._vehicle.get_location())
        # print("current waypoint: ", self._current_waypoint)
        self._vehicle_controller = VehiclePIDController(self._vehicle,
                                                        args_lateral=args_lateral_dict,
                                                        args_longitudinal=args_longitudinal_dict)

        self._global_plan = False

        # compute initial waypoints
        # print("before append len: ", len(self._waypoints_queue))
        # self._waypoints_queue.append()
        # self._waypoints_queue.append( (self._current_waypoint.next(self._sampling_radius)[0], RoadOption.LANEFOLLOW))
        # self._target_road_option = RoadOption.LANEFOLLOW
        # fill waypoint trajectory queue
        # # 计算初始的waypoints
        # self._compute_next_waypoints(k=10)
        # print("after append len: ", len(self._waypoints_queue))


    def set_speed(self, speed):
        """
        Request new target speed.

        :param speed: new target speed in Km/h
        :return:
        """
        self._target_speed = speed

    def _compute_next_waypoints(self, k=1):
        """
        Add new waypoints to the trajectory queue.

        :param k: how many waypoints to compute
        :return:
        """
        # check we do not overflow the queue
        available_entries = self._waypoints_queue.maxlen - len(self._waypoints_queue)
        k = min(available_entries, k)

        for _ in range(k):
            last_waypoint = self._waypoints_queue[-1][0]
            next_waypoints = list(last_waypoint.next(self._sampling_radius))

            if len(next_waypoints) == 1:
                # only one option available ==> lanefollowing
                next_waypoint = next_waypoints[0]
                road_option = RoadOption.LANEFOLLOW
            else:
                # random choice between the possible options
                road_options_list = retrieve_options(
                    next_waypoints, last_waypoint)
                road_option = random.choice(road_options_list)
                next_waypoint = next_waypoints[road_options_list.index(
                    road_option)]

            self._waypoints_queue.append((next_waypoint, road_option))

    def add_waypoint(self, waypoint):
        """
        Add a new specific waypoint to the waypoints buffer
        from the SUMO simulation server.

        :param waypoint: the specific waypoint passed here 
        """
        # print("initial waypoint: ", waypoint)

        # new_point = self._map.get_waypoint(waypoint)
        new_point = self._map.get_waypoint(waypoint.location)
        # print("point lane type:", type(new_point.lane_type))
        # new_point = new_point.get_left_lane().get_left_lane()
        # new_point.
        # print("new fucking waypoint: ", new_point)
        # print("type of new point: ", type(new_point))
        # new_point = carla.Waypoint()
        #print("self.current_waypoint: ", self._current_waypoint)
        # print("waypoint in add_waypoint: ", waypoint)
        # new_point.transform = waypoint
        # new_point.transform.location = waypoint.location
        new_point.transform.rotation = waypoint.rotation
        # # new_point.transform.location.y = waypoint.location.y
        # # new_point.transform.location.z = waypoint.location.z
        # new_point.transform.rotation.pitch = waypoint.rotation.pitch
        # new_point.transform.rotation.yaw = waypoint.rotation.yaw
        # new_point.transform.rotation.roll = waypoint.rotation.roll
        road_option = compute_connection(self._current_waypoint, new_point)
        # print("fucking road option: ", road_option)
        # print("new point: ", new_point)
        self._waypoints_queue.append((new_point, road_option))
        # wp, _ = self._waypoints_queue[-1]
        # wp2, _ = self._waypoints_queue[0]
        # print("element in queue[0]: ", wp2)
        # print("element in queue[-1]: ", wp)
        # print("queue length: ", len(self._waypoints_queue))
        # print("waypoint queue add done in local_planner! current length: ", len(self._waypoints_queue))
    def set_global_plan(self, current_plan):
        self._waypoints_queue.clear()
        for elem in current_plan:
            self._waypoints_queue.append(elem)
        self._target_road_option = RoadOption.LANEFOLLOW
        self._global_plan = True
    
    def get_finished_waypoints(self):
        ret = self.finished_waypoints
        if self.finished_waypoints >= self.message_waypoints:
            self.finished_waypoints = 0
        return ret

    # return True if vehicle is close to the 10th waypoint
    def reached_final_waypoint(self):
        pass
    
    '''
    收到新的action package后丢弃现有的路点缓冲
    '''
    def drop_waypoint_buffer(self):
        self._waypoints_queue.clear()
        self._waypoint_buffer.clear()
        self.finished_waypoints = 0

    def run_step(self, debug=True):
        """
        Execute one step of local planning which involves running the longitudinal and lateral PID controllers to
        follow the waypoints trajectory.

        :param debug: boolean flag to activate waypoints debugging
        :return:
        """
        # print("current queue len: ", len(self._waypoints_queue))
        # print("maxlen: ", int(self._waypoints_queue.maxlen * 0.5))
        # not enough waypoints in the horizon? => add more!
        # if len(self._waypoints_queue) < int(self._waypoints_queue.maxlen * 0.5):
          #  print("no points here!")
           # if not self._global_plan:
               # self._compute_next_waypoints(k=100)

        # # 队列为空时切换到手动操作模式，待修改
       # if len(self._waypoints_queue) == 0:
            #control = carla.VehicleControl()
            #control.steer = 0.0
            #control.throttle = 0.0
            #control.brake = 0.0
            #control.hand_brake = False
            #control.manual_gear_shift = False

           # return control

        #   Buffering the waypoints
        # print("queue length inside run_step: ", len(self._waypoints_queue))
        if not self._waypoint_buffer:
            for i in range(self._buffer_size):
                if self._waypoints_queue:
                    # print("queue length: ", len(self._waypoints_queue))
                    left_point, left_road = self._waypoints_queue.popleft()
                    self._waypoint_buffer.append((left_point, left_road))
                    # right_point, _ = self._waypoint_buffer.popleft()
                    # print("right point is ", right_point)   
                    
                else:
                    break
        # target_waypoint, _ = self._waypoint_buffer[0]
        # print("target_waypoint:", target_waypoint)
        # for i, (waypoint, _) in enumerate(self._waypoint_buffer):
        #     print("waypoint is ", waypoint)
            # time.sleep(2)
        # current vehicle waypoint
        self._current_waypoint = self._map.get_waypoint(self._vehicle.get_location())

        if not self._waypoint_buffer:
            # control = self._vehicle_controller.run_step(0, self._current_waypoint)
            # return control
            return None
           
        self._target_waypoint, self._target_road_option = self._waypoint_buffer[0]
        # for i in range(len(self._waypoint_buffer)):
        #     wp, _ = self._waypoint_buffer[i]
        #     print("waypoint in buffer is ", wp)
        # move using PID controllers
        # print("target_waypoint: ", self._target_waypoint)
        
        control = self._vehicle_controller.run_step(self._target_speed, self._target_waypoint)

        # purge the queue of obsolete waypoints
        vehicle_transform = self._vehicle.get_transform()
        max_index = -1
        # print("len of buffer: ", len(self._waypoint_buffer))
        # for i in range(len(self._waypoint_buffer)):
        #     waypoint = self
        for i, (waypoint, _) in enumerate(self._waypoint_buffer):
            distance = distance_vehicle(waypoint, vehicle_transform)
            # print("min distance: ", self._min_distance, "distance: ", distance)
            # time.sleep(2)
            # 当前车辆和路点的距离小于最小距离，认为已经行驶完成
            if distance < self._min_distance:
                # print("waypoint in enumerate is ", waypoint)
                max_index = i
                
        if max_index >= 0:
            for i in range(max_index + 1):
                self._waypoint_buffer.popleft()
                self.finished_waypoints += 1
                print("current finished waypoints is ", self.finished_waypoints)

            if debug:
                draw_waypoints(self._vehicle.get_world(), [self._target_waypoint], self._vehicle.get_location().z + 1.0)
        # if len(self._waypoint_buffer) == 0:
        #     self.finished_waypoints = self.message_waypoints
        return control


def retrieve_options(list_waypoints, current_waypoint):
    """
    Compute the type of connection between the current active waypoint and the multiple waypoints present in
    list_waypoints. The result is encoded as a list of RoadOption enums.

    :param list_waypoints: list with the possible target waypoints in case of multiple options
    :param current_waypoint: current active waypoint
    :return: list of RoadOption enums representing the type of connection from the active waypoint to each
             candidate in list_waypoints
    """
    options = []
    for next_waypoint in list_waypoints:
        # this is needed because something we are linking to
        # the beggining of an intersection, therefore the
        # variation in angle is small
        next_next_waypoint = next_waypoint.next(3.0)[0]
        link = compute_connection(current_waypoint, next_next_waypoint)
        options.append(link)

    return options


def compute_connection(current_waypoint, next_waypoint):
    """
    Compute the type of topological connection between an active waypoint (current_waypoint) and a target waypoint
    (next_waypoint).

    :param current_waypoint: active waypoint
    :param next_waypoint: target waypoint
    :return: the type of topological connection encoded as a RoadOption enum:
             RoadOption.STRAIGHT
             RoadOption.LEFT
             RoadOption.RIGHT
    """
    n = next_waypoint.transform.rotation.yaw
    n = n % 360.0

    c = current_waypoint.transform.rotation.yaw
    c = c % 360.0

    diff_angle = (n - c) % 180.0
    if diff_angle < 1.0:
        return RoadOption.STRAIGHT
    elif diff_angle > 90.0:
        return RoadOption.LEFT
    else:
        return RoadOption.RIGHT
