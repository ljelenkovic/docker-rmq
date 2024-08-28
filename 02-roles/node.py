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
	def __init__(self, node_name, config, logfile):
		self.node_name = node_name
		self.logfile = logfile

		self.confirm_consume = False

		if config['input']['type'] == 'GEN-MSG':
			self.config_gen(config['input'])

		elif config['input']['type'] == 'queue':
			self.config_input_queue(config['input'])
			self.confirm_consume = True

		else:
			print('? unknown input => ' + str(config['input']['type']))
			sys.exit(1)

		#setup processing
		self.config_processing(config['processing'])

		#setup output
		if config['output']['type'] == 'exchange':
			self.config_output_exchange(config['output'])

		elif config['output']['type'] == 'file':
			self.send_message = self.send_message_file
			self.out_file = config['output']['name']

		elif config['output']['type'] == 'log':
			self.send_message = self.log_msg
		else:
			print('? unknown output => ' + str(config['output']['type']))
			sys.exit(1)

	def log_msg(self, msg):
		if self.logfile:
			with open(self.logfile, "a") as logfile:
				text = '\t'.join([self.node_name, str(datetime.datetime.now()), json.dumps(msg)])
				logfile.write(text + '\n')
	def log(self, text):
		if self.logfile:
			with open(self.logfile, "a") as logfile:
				text = '\t'.join([self.node_name, str(datetime.datetime.now()), text])
				logfile.write(log + '\n')


	# input from 'GEN-MSG'
	def config_gen(self, config):
		self.get_message = self.gen_msg
		self.gen_type = config['interval']['type']
		self.gen_time = config['interval']['time']
		self.gen_next_loop_time = time.time()
		if 'initial-delay' in config:
			self.gen_next_loop_time += config['initial-delay']

	def gen_msg(self):
		# delay node if required
		if self.gen_type == "deterministic" and self.gen_time > 0:
			self.gen_next_loop_time += self.gen_time
		delay = self.gen_next_loop_time - time.time()
		if delay > 0:
			time.sleep(delay)

		#return empty list; in "process" a message will be generated
		return []


	# input from 'queue'
	def config_input_queue(self, config):
		self.get_message = self.get_from_queue
		self.input_exchange_names = config["exchanges"]
		self.input_queue_name = config["queue"]
		self.input_buffer = [] #internal buffer for received messages
		self.bsem = threading.Semaphore(value=1)
		self.msgs = threading.Semaphore(value=0)
		self.consumed = threading.Semaphore(value=0)
		self.ithread = threading.Thread(target = self.input_thread, args=(self,))
		self.ithread.start()

	@staticmethod
	def on_message(channel, method_frame, header_frame, body, args):
		self = args[0]
		msg = body.decode('utf-8')
		msg = json.loads(msg)
		self.bsem.acquire()
		self.input_buffer.append(msg) #critical section
		self.bsem.release()
		self.msgs.release()
		self.consumed.acquire() #wait for message to be consumed
		channel.basic_ack(delivery_tag=method_frame.delivery_tag)

	@staticmethod
	def input_thread(node):
		connection = pika.BlockingConnection(
		    pika.ConnectionParameters(host='localhost'))
		channel = connection.channel()

		for exch in node.input_exchange_names:
			channel.exchange_declare(exchange=exch, exchange_type='fanout')
			result = channel.queue_declare(
					queue=node.input_queue_name,
					exclusive=False, durable=True
				)
			channel.queue_bind(exchange=exch, queue=node.input_queue_name)
		channel.basic_qos(prefetch_count=1)

		on_message_callback = functools.partial(node.on_message, args=(node,))
		channel.basic_consume(
			queue=node.input_queue_name,
			on_message_callback=on_message_callback,
			auto_ack=False
		)
		channel.start_consuming()
		connection.close()

	def get_from_queue(self):
		self.msgs.acquire() # will wait if no message received
		self.bsem.acquire()
		message = self.input_buffer.pop(0)
		self.bsem.release()
		return message


	# processing
	def config_processing(self, config):
		self.skip_processing = 'skip' in config and config['skip'] == True
		if not self.skip_processing:
			self.proc_type = config['duration']['type']
			self.proc_time = config['duration']['time']
			self.proc_val = config['initial-value']

	def process(self, message):
		if self.skip_processing == True:
			return message
	
		if self.proc_type == "deterministic" and self.proc_time > 0:
			time.sleep(self.proc_time)

		# update message: add item to list
		msg = {}
		msg["timestamp"] = str(datetime.datetime.now())
		msg["data"] = '{' + self.node_name + ': ' + str(self.proc_val) + ' }'
		msg["node"] = self.node_name
		self.proc_val += 1

		message.append(msg)

		return message


	# message out to exchange
	def config_output_exchange(self, config):
		self.send_message = self.send_message_exchange
		self.out_exchange = config['name']
		connection = pika.BlockingConnection(
		    pika.ConnectionParameters(host='localhost'))
		self.out_channel = connection.channel()

		self.out_channel.exchange_declare(
			exchange=self.out_exchange,
			exchange_type='fanout'
		)

	def send_message_exchange(self, msg):
		self.out_channel.basic_publish(
			exchange=self.out_exchange,
			routing_key='',
			body=json.dumps(msg),
			properties=pika.BasicProperties(
				delivery_mode = pika.DeliveryMode.Persistent)
		)


	# message out to file
	def send_message_file(self, msg):
		with open(self.out_file, "a") as logfile:
			logfile.write(str(json.dumps(msg)) + '\n')


	def run(self):
		while True:
			msg1 = self.get_message()
			self.log_msg(msg1)

			msg2 = self.process(msg1)

			self.send_message(msg2)
			self.log_msg(msg2)

			#confirm processing of input message
			if self.confirm_consume:
				self.consumed.release()
			#not sure this is working - test it!

if __name__ == '__main__':
	#load config
	if len(sys.argv) < 2:
		print('Usage: ' + sys.argv[0] + ' <node-name>')
		sys.exit(1)

	with open(conf_file, 'r') as f:
		system_config = json.load(f)

	node_name = sys.argv[1]
	if node_name not in system_config:
		print('Node ' + node_name + ' not found in config file ' + conf_file)
		sys.exit(1)
	
	if 'logfile' in system_config:
		logfile = system_config['logfile']
	else:
		logfile = None

	my_node = Node(node_name, system_config[node_name], logfile)
	my_node.run()
