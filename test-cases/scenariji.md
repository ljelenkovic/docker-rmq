# Ispitni scenariji (test caseovi)

## 1. Arhitekture sustava
Arhitekture sustava za sve ispitne uzroke sastoji se od četiri razine, prema slici 1.

```
<ulaz> => {redovi-1} => <obrada-1> => {redovi-2} => <obrada-2> => {redovi-3} => <izlaz>
```
#### *Slika 1. Arhitektura sustava*

U ulaznoj se nalazi čvorovi (ili samo jedan) koji generiraju događaje. To mogu biti događaji okidani vremenom (neki periodički), simulacija ulaza iz vanjskih (drugih) aplikacija, upravljačke poruke poslane izravno od korisnika ili upravljačkog programa ili slično. Ulazni čvorovi svoje događaje oblikuju u poruke (JSON) i šalju ih u ulazne redove označene s `{redovi-1}`.

U drugoj razini nalaze se čvorovi (ili samo jedan) koji čekaju na poruke ulaznih čvorova te ih po primitku obrađuju. Rezultate šalju u redove označene na slici s `{redovi-2}`. Ovisno o scenariju, ovdje također može biti samo jedan čvor ili više njih.

U trećoj razini nalaze se čvorovi (ili samo jedan) koji čekaju na poruke čvorova iz druge razine te ih po primitku obrađuju. Rezultate šalju u redove označene na slici s `{redovi-3}`. Ovisno o scenariju, ovdje također može biti samo jedan čvor ili više njih.

Zadnja četvrta razina zamišljena je za izlazne čvorove. Ti bi čvorovi mogli simulirati vanjske aplikacije koje primaju informacije od testirane, spremnike podataka (dnevnici, baze podataka) i slično.

Predstavljena arhitektura je s jedne strane dovoljno jednostavna, a opet omogućava ispitivanje mnoštvo scenarija.

Svaki čvor se ostvaruje kao zasebna aplikacija, tj. docker slika. Svi redovi poruka ostvaruju se u jednoj zasebnoj slici.

### Dnevnik
U sustavu bu trebao biti još jedan čvor "dnevnik", koji nije prikazan na gornjoj slici.
Ideja je da on prima kopije svih poruka upućenih u sve redove i bilježi ih u dnevnik, a da bi se moglo analizirati rad sustava.
Usluga koja pruža ostvarenje reda poruka ima jednostavne mogućnosti za ostvarenje istoga. Stoga se takav čvor neće posebno isticati u scenarijima.


### Poruka
Obzirom da se poruke šalju u JSON formatu, u svakoj poruci se može zapisati:
- neki kvazi-jedinstveni identifikator poruke
- te za svaku obradu:
  * vrijeme preuzimanja iz reda ili stvaranja
  * vrijeme slanja u red ili pohrane

### Vrijeme
U scenarijima je kao najmanja jedinica vremena uzeta sekunda (iako u nedeterminističkom testu bi onda ponekad bila i manja).
Međutim, može se to skalirati prema potrebi - proći i prilagoditi scenarije s novim vrijednostima vremena.

Ili čak obaviti i ispitivanja sa skaliranjem prema manjim/većim vrijednostima (do neke granice). Npr. napraviti prvo ispitivanje s ovako zadanim, a onda ponoviti s dvostruko kraćim vremenima, pa s četverostruko kraćim itd.

### Upravljanje čvorovima
Svaki čvor je jedna aplikacija pokretana kroz kontejner. Na jednom računalu takvim kontejnerima može upravljati Docker i on bi se prvenstveno koristio. Druga ideja je koristiti Kubernetes ako se koristi raspodijeljeni sustav, ako se slike ne izvode na istom računalu.

# 2. Scenariji


## 2.1. Osnovni način rada

U osnovnom načinu rada bi u svakoj razini bio samo po jedan čvor, prema slici 2.
```
<ulaz> => [red-1] => <obrada-1> => [red-2] => <obrada-2> => [red-3] => <izlaz>
```
#### *Slika 2. Čvorovi u scenariju 1*

Namjena ovog scenarija jest da se ispita osnovna konfiguracija te da se podese vremenska svojstva sustava, tj. kako često generirati poruke, koliko traju obrade i slično. Ideja jest simulirati razne situacije, od "skoro praznog sustava", do sustava u kojem se u (u nekim intervalima) u redovima nalazi barem nekoliko poruka. Isto ponašanje bi se onda iskoristilo u nekim drugim scenarijima i vidjele razlike u ponašanju.

Rad sustava po intervalima:

1. "skoro prazan sustav"
   - trajanje `T1` (20 sekundi)
   - `<ulaz>` generira jednu poruku *"svake dvije sekunde"* i šalje ju u `[red-1]`
   - `<obrada-1>` čeka na poruku iz reda `[red-1]`; po primitku ju obrađuje *"dvije sekunde"*; rezultat šalje u `[red-2]`
   - `<obrada-2>` čeka na poruku iz reda `[red-2]`; po primitku ju obrađuje *"dvije sekunde"*; rezultat šalje u `[red-3]`
   - `<izlaz>` čeka na poruku iz reda `[red-3]`; po primitku ju obrađuje *"jednu sekundu"*; rezultat zapisuje u izlaznu datoteku

2. "povećanje opterećenja"
   - trajanje `T2` (20 sekundi)
   - `<ulaz>` generira jednu poruku *"svake sekunde"* i šalje ju u `[red-1]`
   - ostali čvorovi isto kao i pod 1.

c. "vraćanje u normalu"
   - trajanje `T3` (20 sekundi)
   - ponašanje svih čvorova isto kao i pod 1.

Najprije pokrenuti deterministički sustav gdje *"svake dvije sekunde"* i slično je doslovce svake dvije sekunde. Nakon toga ponovno pokrenuti sustav, ali sada neka se to interpretira *"prosječno vrijeme između dvije poruke neka bude dvije sekunde, koristeći eksponencijalnu razdiobu"*.

U 2. intervalu može se pratiti stanje broja poruka u redovima (možda izravno na neki način, ili posredno preko dnevnika).


## 2.2. Kooperativna obrada

U ovom bi scenariju bilo više čvorova "obrada" u drugom i trećem sloju (barem dva u svakom) koji bi dijelili poslove (svaki bi posao uzeo po jedan čvor za obradu).

```
<ulaz> => [red-1] => { <obrada-1-1>,   => [red-2] => { <obrada-2-1>,   => [red-3] => <izlaz>
                       <obrada-1-2>..}                 <obrada-2-2>..}
```
#### *Slika 3. Čvorovi u scenariju 2*

Ideja je ispitati ponašanje sustava, možda i mogućnosti postavki u usluzi za red poruka, kada obrade poslova ponekad duže (predugo) traju. Kako podesiti ponašanje čvorova, reda poruka i slično, a da poruke kratko čekaju, tj. da podjednako čekaju.

Također se želi ispitati što kada jedan čvor jako dugo radi na poruci (ili ispadne, prekine s radom), da li se ta poruka proslijedi drugom čvoru. Ako da, koliko vremena treba redu za to i može li se to negdje podesiti za red poruka.

## 2.3. Dinamičko aktiviranje čvorova za obradu
U ovom bi scenariju stvorili više radnih čvorova "obrada", ali samo bi jedan bio aktivan (dobivao poruke) dok je sve normalno. Tek kad se broj poruka (ili čekanje poruka u redu) poveća na neke postavljene vrijednosti, onda bi se poruke proslijedile tim dodatnim čvorovima.

Kako to izvesti ovisi o mogućnostima reda poruka (treba li stvoriti nove redove u koje će (neke) poruke ići kad dođe do zagušenja ili sl.).

## 2.3. Dinamičko stvaranje čvorova za obradu
Sličan scenarij prethodnom, ali bi ovdje ispitali mogućnosti dinamičkog stvaranja čvorova kad se dogodi zagušenje (više poruka u nekom redu ili duže čekanje poruka na obradu).

Pitanje je može li se to riješiti samo preko reda poruka ili treba nekako drukčije.

## 2.4. Simulacija pada čvorova
U ovom bi se scenariju ispitale mogućnosti Dockera za ponovno pokretanje čvorova (aplikacija) koje nenadano završe s radom. Ideja je izmjeriti potrebno vrijeme za ponovno pokretanje.

Također, ispitalo bi se kako red reagira na ispad čvora, obzirom da je možda već preuzeo poruku ali nije potvrdio da je ona obrađena i da se može maknuti iz reda.

Moguće bi bilo i umjesto Dockera koristiti druge sustave, npr. Kubernetes (koji može upravljati i raspodijeljenim sustavom, tj. čvorovima na različitim računalima) te izmjeriti njegova vremenska svojstva za detekciju pada čvora i njegovom ponovnom pokretanju.
