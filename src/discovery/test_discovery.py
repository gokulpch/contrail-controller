#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

import gevent
import argparse
import os
import sys
#import discovery.services as services
import discoveryclient.client as client
import uuid
import time
import signal

class TestDiscService():

    def __init__(self, args_str=None):
        self.args = None
        if not args_str:
            args_str = ' '.join(sys.argv[1:])
        self._parse_args(args_str)
    # end __init__

    def _parse_args(self, args_str):

        defaults = {
            'server_ip': '127.0.0.1',
            'server_port': '5998',
            'service_type': None,
            'service_count': 1,
            'remote': None,
            'port': None,
            'service_id': None,
            'admin_state': None,
            'prov_state': None,
            'subscribe_type': None,
            'iterations': 1,
            'delay': 0,
            'send_siul': False,
        }

        # override with CLI options
        parser = argparse.ArgumentParser(
            description="Test Discovery Service")
        parser.add_argument(
            'oper',
            choices=['publish', 'subscribe', 'pubtest', 'subtest', 'update_service', 'pubsub'],
            help="Operation: publish/subscribe/pubtest/subtest/pubsub")
        parser.add_argument(
            '--server_ip', help="Discovery Server IP (default: 127.0.0.1)")
        parser.add_argument(
            '--server_port', help="Discovery Server Port (default: 5998)")
        parser.add_argument('--service_type', help="Service type")
        parser.add_argument(
            '--service_data', help="Service data to publish state of service)")
        parser.add_argument(
            '--service_count', type=int, help="Number of instances. Default is 1")
        parser.add_argument(
            '--remote', help="IP address for publish or subscribe service")
        parser.add_argument('--port', help="Port of service to publish)")
        parser.add_argument('--service_id', help="Service ID of service)")
        parser.add_argument('--admin_state', help="Admin state of service)")
        parser.add_argument(
            '--prov_state', help="Provision state of service)")
        parser.add_argument('--subscribe_type', help="sync or async")
        parser.add_argument(
            '--iterations', type=int, help="Number of iterations for scaled test. Default is 1")
        parser.add_argument(
            '--delay', type=int, help="Delay in seconds between iterations for scaled test. Default is 0")
        parser.add_argument('--send-siul', action="store_true",
            help="Send service-in-use-list attribute in subscribe request")

        parser.set_defaults(**defaults)
        self.args = parser.parse_args(args_str.split())

        if self.args.oper == 'subscribe':
            if self.args.subscribe_type is None:
                print 'Subscribe type (sync or async) must be specified'
                sys.exit()
        elif self.args.oper == 'publish':
            if (self.args.service_data is None or
                    self.args.service_type is None):
                print 'Service name and data required for publish operation'
                sys.exit()
        elif self.args.oper == 'pubtest':
            if self.args.service_type is None:
                print 'Service name required for publish operation'
                sys.exit()

        print 'Discovery server = %s:%s'\
            % (self.args.server_ip, self.args.server_port)
        print 'Service type = ', self.args.service_type
        print 'Instance count = ', self.args.service_count
    # end _parse_args

x = None
disc = None
server_list = {}
subtask_dict = {}

def info_callback(info, client_id):
    global x
    global server_list
    global subtask_dict
    print 'In subscribe callback handler'
    print '%s' % (info)
    server_list[client_id] = [entry['@publisher-id'] for entry in info]
    if x.args.send_siul:
        sub_obj = subtask_dict[client_id]
        sub_obj.update_subscribe_data('service-in-use-list', {'publisher-id':server_list[client_id]})
        print 'Setting service-in-use-list to %s' % server_list[client_id]

def ctrl_c_handler(signal, frame):
    print disc.get_stats()
    sys.exit(0)

signal.signal(signal.SIGINT, ctrl_c_handler)
def main(args_str=None):
    global x
    global disc
    x = TestDiscService(args_str)
    _uuid = str(uuid.uuid4())
    myid = 'test_disc:%s' % (_uuid[:8])
    disc = client.DiscoveryClient(
        x.args.server_ip, x.args.server_port, "test-discovery",
            pub_id = "test-discovery-%d" % os.getpid())
    if x.args.remote:
        disc.set_myip(x.args.remote)

    if x.args.oper == 'subscribe':
        print 'subscribe: service-type = %s, count = %d, myid = %s,\
            subscribe type: %s' \
            % (x.args.service_type, x.args.service_count, myid, x.args.subscribe_type)

        # sync
        if x.args.subscribe_type == 'sync':
            obj = disc.subscribe(x.args.service_type, x.args.service_count)
            print obj.info
        else:
        # async
            obj = disc.subscribe(
                x.args.service_type, x.args.service_count, info_callback)
            gevent.joinall([obj.task])
    elif x.args.oper == 'publish':
        print 'Publish: service-type %s info %s' \
            % (x.args.service_type, x.args.service_data)
        pubdata = {x.args.service_type : x.args.service_data}
        task = disc.publish(x.args.service_type, pubdata)
        gevent.joinall([task])
    elif x.args.oper == 'pubsub':
        print 'PubSub: service-type %s info %s' \
            % (x.args.service_type, x.args.service_data)
        pubdata = {x.args.service_type : x.args.service_data}
        pubtask = disc.publish(x.args.service_type, pubdata)
        subobj = disc.subscribe(
            x.args.service_type, x.args.service_count, info_callback)
        gevent.joinall([pubtask, subobj.task])
    elif x.args.oper == 'pubtest':
        tasks = []
        for i in range(x.args.iterations):
            pub_id = "disco-%d-%i" % (os.getpid(), i)
            disc = client.DiscoveryClient(
                x.args.server_ip, x.args.server_port, 
                    pub_id, pub_id)
            pubdata = {x.args.service_type : '%s-%d' % (x.args.service_type, i)}
            print 'Publish: service-type %s, data %s'\
                % (x.args.service_type, pubdata)
            task = disc.publish(x.args.service_type, pubdata)
            tasks.append(task)
            if x.args.delay:
                time.sleep(x.args.delay)
        gevent.joinall(tasks)
    elif x.args.oper == 'subtest':
        global subtask_dict
        tasks = []
        for i in range(x.args.iterations):
            client_id = "test-discovery-%d-%d" % (os.getpid(), i)
            disc = client.DiscoveryClient(
                x.args.server_ip, x.args.server_port, client_id)
            obj = disc.subscribe(
                      x.args.service_type, x.args.service_count, info_callback, client_id)
            tasks.append(obj.task)
            if x.args.delay:
                time.sleep(x.args.delay)
            subtask_dict[client_id] = obj
        print 'Started %d tasks to subscribe service %s, count %d' \
            % (x.args.iterations, x.args.service_type, x.args.service_count)
        gevent.joinall(tasks)
    elif x.args.oper == 'update_service':
        if x.args.service_id is None:
            print 'Error: Missing service ID'
            sys.exit(1)
        elif x.args.admin_state is None and x.args.prov_state is None:
            print 'Error: Admin state of Provison state must be specified'
            sys.exit(1)
        print 'Update service %s, admin state "%s", prov state "%s"' \
            % (x.args.service_id, x.args.admin_state or '',
               x.args.prov_state or '')
        entry = disc.get_service(x.args.service_id)
        if entry is None:
            print 'Error: Service info not found!'
            sys.exit(1)
        print 'Entry = ', entry
        if x.args.admin_state:
            entry['admin_state'] = x.args.admin_state
        if x.args.prov_state:
            entry['prov_state'] = x.args.prov_state
        rv = disc.update_service(x.args.service_id, entry)
        print 'Update srevice rv = ', rv

if __name__ == "__main__":
    main()
