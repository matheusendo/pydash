# -*- coding: utf-8 -*-
"""
Algoritmo baseado no modelo proposto no artigo Probe and Adapt: Rate Adaptation for HTTP Video
Streaming At Scale.


"""
import timeit
import statistics 
from player.parser import *
from r2a.ir2a import IR2A

class R2APanda(IR2A):
    
    def __init__(self, id):
        IR2A.__init__(self, id)
        self.lista_vazao_estimada = []
        self.lista_vazao_calc = []
        self.buffer = (0,0)
        self.tamanho_buffer = 0
        self.buffer_suficiente = 100
        self.start = 0
        self.stop = 0
        self.vazao = 0.0
        self.vazao_suavizada = 0.0
        self.k = 0.14 # k deve ser menor que 2/duração do segmento de vídeo(1 no caso)
        self.w = 0.3
        self.t = []
        self.parsed_mpd = ''
        self.qi = []


    def estima_vazao(self):
        #Faz a estimação da vazão, utiliza a fórmula descrita no artigo Probe and Adapt com adaptação em relação ao tempo t(limitando ele a 5)
        self.vazao=self.lista_vazao_estimada[-1]+(self.t[-1]*self.k*(self.w-max(0,(self.lista_vazao_estimada[-1]-self.lista_vazao_calc[-1]+self.w))))

        return self.vazao

    def handle_xml_request(self, msg):
        self.send_down(msg)

    def handle_xml_response(self, msg):
        # getting qi list
        self.parsed_mpd = parse_mpd(msg.get_payload())
        self.qi = self.parsed_mpd.get_qi()

        self.send_up(msg)

    def panda(self,buffer1):

        #Primeira Parte do modelo PANDA, faz uma calculo para estimar a vazão e a adiciona a lista de vazoes estimadas
        max_buffer=self.whiteboard.max_buffer_size
        self.vazao=self.estima_vazao()
        self.lista_vazao_estimada.append(self.vazao)

        #Segunda Parte faz a suavização da estimação, a fim de remover outliers, fazendo a média harmônica das últimas 20 estimações, 
        #se não tiverem sido feitas 20 ainda faz a média harmônica de todas estimações até o momento
        
        vazao_suavizada=statistics.harmonic_mean(self.lista_vazao_estimada[-20:])
           

        #Terceira Parte faz a trasformação da vazão suavizada para a qualidade indicada, levando em conta também o buffer

        for i in range(19):
            if i==0 and vazao_suavizada<=self.qi[0] and buffer1<max_buffer/4:
                return self.qi[0]
            elif i==0 and vazao_suavizada<=self.qi[0] and buffer1>max_buffer/4:
                return self.qi[4]
            elif self.qi[i+1]>=vazao_suavizada>=self.qi[i] and buffer1<max_buffer/4:
                if vazao_suavizada-self.qi[i]>=self.qi[i+1]-vazao_suavizada:
                    return self.qi[min(i+1,buffer1)]
                else:
                    return self.qi[min(i,buffer1)]
            elif self.qi[i+1]>=vazao_suavizada>=self.qi[i] and buffer1>max_buffer/4:
                return self.qi[i+1]
            
        return self.qi[0]

    def handle_segment_size_request(self, msg):
        # time to define the segment quality choose to make the request
        
        
        self.lista_buffer=self.whiteboard.get_playback_buffer_size()

        #Caso seja a primeira iteração a lista de buffer está vazia e automaticamente escolhe a qualidade 0
        
        if len(self.lista_buffer)==0:
            msg.add_quality_id(self.qi[0])
        #Caso não esteja 
        elif len(self.lista_buffer)!=0:
            self.buffer = self.lista_buffer[-1]
            self.tamanho_buffer = self.buffer[1]
            #Se o tamanho do buffer for maior ou igual ao valor de buffer suficiente escolhe a qualidade máxima
            if self.tamanho_buffer>=self.buffer_suficiente:
                msg.add_quality_id(self.qi[19])
            #Se o tamanho do buffer for 0 escolhe a qualidade 0
            elif self.tamanho_buffer==0:
                msg.add_quality_id(self.qi[0])
            #Caso o buffer esteja entre 0 e o valor de buffer suficiente utiliza panda para indicar a qualidade
            elif self.lista_vazao_calc:
                msg.add_quality_id(self.panda(self.tamanho_buffer))

        #Começa a contagem do tempo
        self.start = timeit.default_timer()
        self.send_down(msg)

    def handle_segment_size_response(self, msg):
        #Para a contagem do tempo e calcula a diferença para o calculo da vazao
        self.stop = timeit.default_timer()
        
        self.t.append(self.stop-self.start)
        self.lista_vazao_calc.append(msg.get_bit_length()/self.t[-1])
        #Caso seja a primeira iteração(lista de vazao estimada vazia) a vazao estimada é igual a calculada
        if len(self.lista_vazao_estimada)==0:
            self.lista_vazao_estimada.append(msg.get_bit_length()/self.t[-1])

        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass

