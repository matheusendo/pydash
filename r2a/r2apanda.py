# -*- coding: utf-8 -*-
"""
Algoritmo baseado no modelo proposto no artigo Probe and Adapt: Rate Adaptation for HTTP Video
Streaming At Scale.
Matheus Eiji Endo - 15/0018169
Johannes Peter Schulte - 15/0132662
"""
import timeit
import time
import statistics 
from player.parser import *
from r2a.ir2a import IR2A

class R2APanda1(IR2A):
    
    def __init__(self, id):
        IR2A.__init__(self, id)
        self.lista_vazao_estimada = [] #Lista das vazões estimadas
        self.lista_vazao_calc = [] #Lista das vazões calculadas
        self.lista_vazao_suavizada = [] # Lista das vazões suavizadas
        self.lista_r = [] # Lista das qualidades escolhidas
        self.buffer_minimo = 26 # Buffer mínimo
        self.beta = 0.2 # Utilizado no calculo da tempo estimado
        self.alpha = 0.2 # Utilizado no calculo da suavização da vazao
        self.k = 0.14 # Utilizado no calculo da vazao estimada, k deve ser menor que 2/duração do segmento de vídeo(1 no caso)
        self.w = 0.3 # Utilizado no calculo da vazao estimada
        self.start = 0 # Tempo para cálculo da vazão
        self.t_estimado = [0] # Lista dos tempos estimados
        self.t = [] # Lista dos tempos
        self.parsed_mpd = '' # Parser utilizado para as qualidades
        self.qi = [] # Lista das qualidades


    def estima_vazao(self):
        tempo=max(self.t[-1],self.t_estimado[-1]) # Escolha de T sendo o máximo do tempo estimado ou tempo calculado
        # Aqui há uma alteração do modelo do artigo
        # Se a última vazão estimada foi menor do que a calculada, fazer o cálcula de forma a aumentar a vazão estimada, se não utiliza a fórmula igual do artigo 
        if self.lista_vazao_estimada[-1]<self.lista_vazao_calc[-1]:
            vazao=self.lista_vazao_estimada[-1]+((tempo)*self.k*(self.w+max(0,(self.lista_vazao_calc[-1]-self.lista_vazao_estimada[-1]+self.w))))
        else:
            vazao=self.lista_vazao_estimada[-1]+((tempo)*self.k*(self.w-max(0,(self.lista_vazao_estimada[-1]-self.lista_vazao_calc[-1]+self.w))))
        
        
        #Retorna a vazao, se ela for muita baixa, retorna vazao igual à da menor qualidade, uma vez que é garantido que a vazão mínima é essa
        return max(vazao,self.qi[0])

    def handle_xml_request(self, msg):
        # Começa a marcação do tempo
        self.start = time.perf_counter()
        self.send_down(msg)

    def handle_xml_response(self, msg):
        # Pega a lista de qualidades
        self.parsed_mpd = parse_mpd(msg.get_payload())
        self.qi = self.parsed_mpd.get_qi()
        # Calcula o tempo decorrido
        self.t.append(time.perf_counter() - self.start)
        # Calcula a vazao inicial baseada no pedido do xml, e coloca nas listas das vazões, uma vez que é a primeira
        self.lista_vazao_calc.append(msg.get_bit_length() / self.t[-1])
        self.lista_vazao_suavizada.append(msg.get_bit_length() / self.t[-1])
        self.lista_vazao_estimada.append(msg.get_bit_length() / self.t[-1])
        # Primeiro valor da lista de qualidades é feito de forma artificial, baseado na vazao calculada anteriormente
        for i in range(19,0,-1):
            if (self.lista_vazao_calc[-1])>=self.qi[i]:
                self.lista_r.append(i)

        self.send_up(msg)

    def panda(self):

        # Funcao para a escolha da qualidade segundo artigo, com algumas modificações

        # Pega a lista de buffers
        lista_buffer=self.whiteboard.get_playback_buffer_size()

        # Pega os dois últimos buffers, se só houver um , ambos são igualados
        if len(lista_buffer) < 2:
            buffer = lista_buffer[-1]
            buffer_antigo = buffer
        else:
            buffer = lista_buffer[-1]
            buffer_antigo = lista_buffer[-2]
        
        # Primeira parte, estima a vazao e coloca na lista
        vazao=self.estima_vazao()
        self.lista_vazao_estimada.append(vazao)

        #Segunda Parte faz a suavização da estimação 
        #escolhe o tempo maximo, entre o calculado e estimado
        tempo = max(self.t[-1],self.t_estimado[-1])
        # Faz a suavização da vazao de acordo com o artigo
        vazao_suavizada=((-self.alpha*(self.lista_vazao_suavizada[-1]-self.lista_vazao_estimada[-1]))*tempo)+self.lista_vazao_suavizada[-1]
        self.lista_vazao_suavizada.append(vazao_suavizada)
           

        #Terceira Parte faz a trasformação da vazão suavizada para a qualidade indicada, levando em conta também o buffer
        # Definação dos thresholds, r_up e r_down, e das margens de segurança delta_up e delta_down
        delta_up=0.15*vazao_suavizada
        delta_down=0
        r_up=-1
        r_down=-1

        #Caso a vazao suavizada - a margem delta_up for menor que a menor qualidade, atribui a qualidade mínima a r_up, a não ser que o buffer tenha crescido
        if (vazao_suavizada-delta_up)<self.qi[0] and buffer[1]<buffer_antigo[1]:
            r_up=0
        elif (vazao_suavizada-delta_up)<self.qi[0] and buffer[1]>=buffer_antigo[1]:
            r_up=1

        # mesma coisa para a r_down
        if (vazao_suavizada-delta_down)<self.qi[0] and buffer[1]<buffer_antigo[1]:
            r_down=0
        elif (vazao_suavizada-delta_down)<self.qi[0] and buffer[1]>=buffer_antigo[1]:
            r_down=1

        # defines r_up e r_down, de acordo com o artigo, sendo a qualidade maxima dado que esta deve ser maior ou igual que a vazao suavizada - as margens de segurança
        for i in range(19,-1,-1):
            if (vazao_suavizada-delta_up)>=self.qi[i] and r_up==-1:
                r_up=i
            if (vazao_suavizada-delta_down)>=self.qi[i] and r_down==-1:
                r_down=i

        # Pega a ultima qualidade
        r_1=self.lista_r[-1]

        # se o buffer for muito baixo escolhe a qualidade automaticamente, se não utiliza a abordagem do artigo
        if buffer[1]<=1:
            r=0
        elif r_1<r_up :
            r=r_up
        elif r_up<=r_1<=r_down :
            r=r_1
        else:
            r=r_down
        
        
        self.lista_r.append(r)
        return self.qi[r]
        

        
        

    def handle_segment_size_request(self, msg):
        # Pega os buffers
        lista_buffer=self.whiteboard.get_playback_buffer_size()

        #Caso seja o primeiro segmento a lista de buffer está vazia e automaticamente escolhe a qualidade 0
        #Porem é preciso atualizar as vazoes
        if len(lista_buffer)==0:
            msg.add_quality_id(self.qi[0])
            self.lista_r.append(0)
            vazao=self.estima_vazao()
            self.lista_vazao_estimada.append(vazao)
            tempo=max(self.t[-1],self.t_estimado[-1])
            vazao_suavizada=((self.beta*(self.lista_vazao_suavizada[-1]-self.lista_vazao_estimada[-1]))*tempo)+self.lista_vazao_suavizada[-1]
            self.lista_vazao_suavizada.append(vazao_suavizada)
        #Caso não esteja utiliza a panda
        elif len(lista_buffer)!=0:
            msg.add_quality_id(self.panda())
                
        # se a lista de buffer estiver vazia considera o buffer sendo 0 para o tempo
        if(len(lista_buffer)==0):
            buffer=[0,0]
        else:
            buffer=lista_buffer[-1]
        # Faz a estimacao do tempo, seguindo o artigo
        tempo=(self.lista_r[-1]/self.lista_vazao_suavizada[-1])+(self.beta*(buffer[1]-self.buffer_minimo))
        self.t_estimado.append(tempo)

        #Começa a contagem do tempo
        self.start = time.perf_counter()
        self.send_down(msg)

    def handle_segment_size_response(self, msg):
        #Para a contagem do tempo e calcula a diferença para o calculo da vazao
        self.t.append(time.perf_counter() - self.start)
        self.lista_vazao_calc.append(msg.get_bit_length()/self.t[-1])
        
        

        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass