#!/usr/bin/env python
import sys
import pika
import json
import threading
import time
import datetime
import ctypes

node = None
input_file = None
output_file = None

counter = 0

def log(event, message):
	msg = " - ".join((str(datetime.datetime.now()), node['name'], event, message))
	print(msg)
	with open("log.txt", "a") as logfile:
		logfile.write(msg + '\n')

# message queue wrappers
input = [] #internal buffer for received messages
bsem_input = threading.Semaphore(value=1)
sem_input = threading.Semaphore(value=0)
sem_input_consumed = threading.Semaphore(value=0)
output_channel = None

def mq_setup_input_queue():
	def on_message(channel, method_frame, header_frame, body):
		msg = body.decode('utf-8')
		#print(str(node['name']) + " received: " + str(msg))
		log('received', msg)
		bsem_input.acquire()
		input.append(msg)
		bsem_input.release()
		sem_input.release()
		#wait for message to be consumed?
		sem_input_consumed.acquire()
		channel.basic_ack(delivery_tag=method_frame.delivery_tag)

	def input_thread():
		input_mq = pika.BlockingConnection(
			pika.ConnectionParameters(host="localhost"),
		)
		input_channel = input_mq.channel()
		input_channel.queue_declare(queue=node['input']['name'])
		input_channel.basic_qos(prefetch_count=1)
		input_channel.basic_consume(
			queue=node['input']['name'],
			on_message_callback=on_message
		)
		try:
			input_channel.start_consuming()
		except KeyboardInterrupt:
			input_channel.stop_consuming()
		input_mq.close()

	thread = threading.Thread(target = input_thread)
	thread.start()

def mq_setup_output_queue():
	global output_channel, output_mq
	output_mq = pika.BlockingConnection(
		pika.ConnectionParameters(host='localhost'),
	)
	output_channel = output_mq.channel()
	output_channel.queue_declare(queue=node['output']['name'])

def mq_send_message(message):
	global output_channel
	output_channel.basic_publish(
		exchange='',
		routing_key=node['output']['name'],
		body=message,
	)

def mq_get_message():
	sem_input.acquire() # will wait if no message received
	bsem_input.acquire()
	message = input.pop(0)
	bsem_input.release()
	return message

def get_message():
	if node['input']['type'] == 'GEN-SEQ':
		message = node['input']['prefix']
		type = 'generated'
	elif node['input']['type'] == 'FILE':
		message = input_file.readline()
		type = 'from file'
	elif node['input']['type'] == 'STDIN':
		message = input_file.readline()
		type = 'from stdin'
	elif node['input']['type'] == 'queue':
		message = mq_get_message()
		type = 'from queue ' + node['input']['name']

	log(type, message)
	return message


def send_message(message):
	if node['output']['type'] == 'FILE':
		output_file.write(message + '\n')
		type = 'saved to file'
	elif node['output']['type'] == 'STDOUT':
		output_file.write(message + '\n')
		type = 'printed on stdout'
	elif node['output']['type'] == 'queue':
		mq_send_message(message)
		type = 'sent to queue ' + node['output']['name']

	log(type, message)

	#enable new message reception
	if node['input']['type'] == 'queue':
		sem_input_consumed.release()

def setup():
	global input_file, output_file, node, counter

	if len(sys.argv) < 2:
		print('Usage: ' + sys.argv[0] + ' <node-name>')
		sys.exit(1)

	with open('config.json', 'r') as f:
		config = json.load(f)
	#print(json.dumps(config, indent=2))
	for x in config:
		if x['name'] == sys.argv[1]:
			node = x
			break
	else:
		print('Node ' + sys.argv[1] + ' not found in config.json')
		sys.exit(1)

	if node['input']['type'] == 'GEN-SEQ':
		#print('input = GEN-SEQ')
		pass
	elif node['input']['type'] == 'FILE':
		#print('input = FILE')
		input_file = open(node['input']['file'])
	elif node['input']['type'] == 'STDIN':
		#print('input = FILE')
		input_file = sys.stdin
	elif node['input']['type'] == 'queue':
		#print('input = queue')
		mq_setup_input_queue()
	else:
		print('input = ? ' + str(node['input']['type']))
		sys.exit(1)

	counter = node['loop-processing']['initial-value']

	if node['output']['type'] == 'FILE':
		#print('output = FILE')
		output_file = open(node['output']['file'])
	elif node['output']['type'] == 'STDOUT':
		#print('output = STDOUT')
		output_file = sys.stdout
	elif node['output']['type'] == 'queue':
		#print('output = queue')
		mq_setup_output_queue()
	else:
		print('output = ? ' + str(node['output']['type']))
		sys.exit(1)

def main_loop():
	global counter
	while True:
		message = get_message()
		time.sleep(1)
		message +=  '{' + str(counter) + '}' + node['output']['append']
		counter += 1
		send_message(message)
		time.sleep(5)

if __name__ == '__main__':
	try:
		setup()
		main_loop()
	except KeyboardInterrupt:
		pass

	log('exiting', '')
	print('press Ctrl+C (again) to interrupt receiver thread')
