#!/usr/bin/env python
import sys
import pika
import json
import threading
import time
import datetime
import ctypes
import functools

conf_file = 'config.json'

class Node:
	def __init__(self, name, config, log=False):
		self.name = name
		self.log = log
		self.logfile = config['logfile']

		if name not in config:
			print('Node ' + name + ' not found in config file')
			sys.exit(1)

		self.myconf = config[name]
		self.config() # continue setup

	def log_msg(self, msg):
		if self.log:
			with open(self.logfile, "a") as logfile:
				text = '\t'.join([self.name, str(datetime.datetime.now()), json.dumps(msg)])
				logfile.write(text + '\n')
	def log(self, text):
		if self.log:
			with open(self.logfile, "a") as logfile:
				text = '\t'.join([self.name, str(datetime.datetime.now()), text])
				logfile.write(log + '\n')

	# input from 'GEN-MSG'
	def gen_msg(self):
		# delay if required
		if self.gen_initial_delay:
			self.gen_next_loop_time += self.gen_initial_delay
		elif self.gen_type == "deterministic" and self.gen_time > 0:
			self.gen_next_loop_time += self.gen_time
		delay = self.gen_next_loop_time - time.time()
		if delay > 0:
			time.sleep(delay)

		'''
		# generate message
		msg = {}
		msg["timestamp"] = str(datetime.datetime.now())
		msg["data"] = '{' + self.name + ': ' + str(self.proc_val) + ' }'
		msg["node"] = self.name
		self.proc_val += 1
		'''
		#return empty list; in process will be generate a message

		return []

	def config_gen(self, cnf):
		self.get_message = self.gen_msg
		self.gen_type = cnf['interval']['type']
		self.gen_time = cnf['interval']['time']
		self.gen_initial_delay = cnf['initial-delay']
		#self.gen_prefix = cnf['prefix']
		self.gen_next_loop_time = time.time()

	# input from 'queue'
	@staticmethod
	def on_message(channel, method_frame, header_frame, body, args):
		self = args[0]
		msg = body.decode('utf-8')
		msg = json.loads(msg) #json.dumps(x)
		self.bsem.acquire()
		self.input_buffer.append(msg) #critical section
		self.bsem.release()
		self.msgs.release()
		self.consumed.acquire() #wait for message to be consumed
		channel.basic_ack(delivery_tag=method_frame.delivery_tag)

	@staticmethod
	def input_thread(self):
		connection = pika.BlockingConnection(
		    pika.ConnectionParameters(host='localhost'))
		channel = connection.channel()

		for exch in self.input_exchange_names:
			channel.exchange_declare(exchange=exch, exchange_type='fanout')
			result = channel.queue_declare(
					queue=self.input_queue_name,
					exclusive=False, durable=True
				)
			channel.queue_bind(exchange=exch, queue=self.input_queue_name)
		channel.basic_qos(prefetch_count=1)

		on_message_callback = functools.partial(self.on_message, args=(self,))
		channel.basic_consume(
			queue=self.input_queue_name,
			on_message_callback=on_message_callback,
			auto_ack=False
		)
		channel.start_consuming()
		connection.close()

	def config_input_queue(self, cnf):
		self.get_message = self.get_from_queue
		self.input_exchange_names = cnf["exchanges"]
		self.input_queue_name = cnf["queue"]
		self.input_buffer = [] #internal buffer for received messages
		self.bsem = threading.Semaphore(value=1)
		self.msgs = threading.Semaphore(value=0)
		self.consumed = threading.Semaphore(value=0)
		self.ithread = threading.Thread(target = self.input_thread, args=(self,))
		self.ithread.start()

	def get_from_queue(self):
		self.msgs.acquire() # will wait if no message received
		self.bsem.acquire()
		message = self.input_buffer.pop(0)
		self.bsem.release()
		return message

	# processing
	def config_processing(self, cnf):
		self.proc_type = cnf['duration']['type']
		self.proc_time = cnf['duration']['time']
		self.proc_val = cnf['initial-value']
		#self.proc_append = cnf['append']

	def process(self, message):
		if self.proc_type == "deterministic" and self.proc_time > 0:
			time.sleep(self.proc_time)

		# update message: add item to list
		msg = {}
		msg["timestamp"] = str(datetime.datetime.now())
		msg["data"] = '{' + self.name + ': ' + str(self.proc_val) + ' }'
		msg["node"] = self.name
		self.proc_val += 1

		message.append(msg)

		return message

	# message out to exchange
	def send_message_exchange(self, msg):
		self.out_channel.basic_publish(
			exchange=self.out_exch,
			routing_key='',
			body=json.dumps(msg),
			properties=pika.BasicProperties(
				delivery_mode = pika.DeliveryMode.Persistent)
		)

	def config_output_exchange(self, cnf):
		self.send_message = self.send_message_exchange
		self.out_exch = cnf['name']
		connection = pika.BlockingConnection(
		    pika.ConnectionParameters(host='localhost'))
		self.out_channel = connection.channel()

		self.out_channel.exchange_declare(
			exchange=self.out_exch,
			exchange_type='fanout'
		)

	# message out to file
	def send_message_file(self, msg):
		with open(self.out_file, "a") as logfile:
			logfile.write(str(json.dumps(msg)) + '\n')


	# setup
	def config(self):
		#setup input
		if self.myconf['input']['type'] == 'GEN-MSG':
			self.config_gen(self.myconf['input'])

		elif self.myconf['input']['type'] == 'queue':
			self.config_input_queue(self.myconf['input'])
		else:
			print('? unknown input => ' + str(self.myconf['input']['type']))
			sys.exit(1)

		#setup processing
		self.config_processing(self.myconf['processing'])

		#setup output
		if self.myconf['output']['type'] == 'exchange':
			self.config_output_exchange(self.myconf['output'])

		elif self.myconf['output']['type'] == 'file':
			self.send_message = self.send_message_file
			self.out_file = self.myconf['output']['name']

		elif self.myconf['output']['type'] == 'log':
			self.send_message = self.log_msg
		else:
			print('? unknown output => ' + str(self.myconf['output']['type']))
			sys.exit(1)


	def run(self):
		while True:
			msg1 = self.get_message()
			self.log_msg(msg1)

			msg2 = self.process(msg1)

			self.send_message(msg2)
			self.log_msg(msg2)

			#confirm processing of input message
			if self.myconf['input']['type'] == 'queue':
				self.consumed.release()
			#not sure this is working - if interrupted msg is still lost

		print('press Ctrl+C (again) to interrupt receiver thread')

if __name__ == '__main__':
	#load config
	if len(sys.argv) < 2:
		print('Usage: ' + sys.argv[0] + ' <node-name>')
		sys.exit(1)
	with open(conf_file, 'r') as f:
		config = json.load(f)

	my_node = Node(sys.argv[1], config, log=True)
	my_node.run()
