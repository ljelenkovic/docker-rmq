# Testiranje stabilnosti korištenjem dockera

Ideja je automatski upravljati docker slikama u kojima se vrte aplikacije tako
da ako nešto ispadne se brzo oporavi (restarta ili pokrene novi).

## 00-hello
U "00-hello" je primjer "Hello world" koji koristi tri kontejnera:
1. RabbitMQ server
2. Python program koji šalje poruke
3. Python program koji prima poruke

U "upute.txt" nalaze se upute kako sve posložiti.

## 01-chain
Primjer tri aplikacije:
- prva (node-1) generira podatke i šalje ih u red mq1
- druga čita iz mq1, "obrađuje" i šalje u mq2
- treća čita iz mq2, "obrađuje" i šalje "van" (ispiše)

