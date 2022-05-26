# -*- coding: utf-8 -*-
import math 

bBoxMaxX = []
bBoxMinX = []
bBoxMaxY = []
bBoxMinY = []


def rastojanje(koordinata1, koordinata2):
        k1 = koordinata1.split(' ')
        k2 = koordinata2.split(' ')

        x1 = float(k1[0])
        y1 = float(k1[1])
        x2 = float(k2[0])
        y2 = float(k2[1])
                   
        ras = math.sqrt((x1-x2)*(x1-x2)+(y1-y2)*(y1-y2))
        return ras
        

def presloziRasporedTacaka(koord):
        maxRastojanje = rastojanje(koord[0], koord[len(koord)-1])
        #print("na ", maxRastojanje)
        lokacijaMaxRastojanja = 0
        
        for i in range(1, len(koord)):
                tmpRastojanje = rastojanje(koord[i-1], koord[i])
                #print(i, tmpRastojanje)
                if(tmpRastojanje > maxRastojanje):
                        maxRastojanje = tmpRastojanje
                        lokacijaMaxRastojanja = i
        tmp = koord[lokacijaMaxRastojanja:] + koord[0:lokacijaMaxRastojanja]
        #print("prekida na ", lokacijaMaxRastojanja, " od ", len(koordinate), maxRastojanje)
        return tmp
        

def daLiSuDovoljnoBlizu(i, j):
	if(
		((bBoxMaxX[i] >= bBoxMinX[j] - 1000 and  bBoxMinX[i] - 1000 <= bBoxMinX[j])
                 or
                 (bBoxMaxX[i] >= bBoxMaxX[j] - 1000 and  bBoxMinX[i] - 1000 <= bBoxMaxX[j])
                 )
		and
		((bBoxMaxY[i] >= bBoxMinY[j] - 1000 and  bBoxMinY[i] - 1000 <= bBoxMinY[j])
                 or
                 (bBoxMaxY[i] >= bBoxMaxY[j] - 1000 and  bBoxMinY[i] - 1000 <= bBoxMaxY[j]))
		):
		return True
	else:
		#print("   nema preklapanja")
		return False


out = open("izlaz.csv", "w", encoding='utf8')

lines = []
with open(r'naselje.csv', 'r', encoding='utf8') as f: # open csv file
#with open(r'kraljevo.csv', 'r', encoding='utf8') as f: # open csv file
#with open(r'titel.csv', 'r', encoding='utf8') as f: # open csv file
    for line in f:
        lines.append(str(line))

bBoxMaxX = len(lines)*[None]
bBoxMinX = len(lines)*[None]
bBoxMaxY = len(lines)*[None]
bBoxMinY = len(lines)*[None]

print("Ucitava podatke...")

#racuna bounding box za svaku opstinu
for i in range(1, len(lines)):
	p = lines[i].rfind('((') + 2
	k = lines[i].find(')', p)
	koordinate = lines[i][p:k].split(',')

	xMin = 9999999999
	xMax = 0
	yMin = 9999999999
	yMax = 0
	
	for koordinata in koordinate:
		x = float(koordinata.split(' ')[0])
		y = float(koordinata.split(' ')[1])
		if(x < xMin):
			xMin = x
		if(x > xMax):
			xMax = x
		if(y < yMin):
			yMin = y
		if(y > yMax):
			yMax = y

	#print(i, xMin, xMax, yMin, yMax)

	bBoxMaxX[i] = xMax
	bBoxMinX[i] = xMin
	bBoxMaxY[i] = yMax
	bBoxMinY[i] = yMin

for i in range(1, len(lines)):
	p = lines[i].rfind('(')+1
	k = lines[i].find(')')
	koordinate = lines[i][p:k].split(',')

	naziv = lines[i].split(',')[2]
	print("Ispituje", i)
	
	for j in range(i+1, len(lines)):
		if(daLiSuDovoljnoBlizu(i, j)):
#			print(i, j, naziv)
			preklapanje = []
			for koordinata in koordinate:
				#if(koordinata in lines[j] and not (koordinata in preklapanje)):
				if(koordinata in lines[j]):                                        
					preklapanje.append(koordinata)

			if(len(preklapanje)>1):
				naziv2 = lines[j].split(',')[2]
				preslozeno = presloziRasporedTacaka(preklapanje)
				print(naziv, naziv2)
				out.write('{},{},\"LINESTRING({})\",\"POINT({})\"\n'.format(naziv,naziv2, ",".join(preslozeno[0:len(preslozeno)]), preslozeno[0]))

out.close()
