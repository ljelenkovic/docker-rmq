#!/usr/bin/env python
import pika

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

channel.exchange_declare(exchange='logs', exchange_type='fanout')

message = "Hello World!"
channel.basic_publish(exchange='logs', routing_key='', body=message,
properties=pika.BasicProperties(delivery_mode = pika.DeliveryMode.Persistent))

connection.close()
