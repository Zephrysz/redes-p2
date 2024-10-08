import asyncio
import os 
import time 
import math

from grader.tcputils import *


class Servidor:
    def __init__(self, rede, porta):
        self.rede = rede
        self.porta = porta
        self.conexoes = {}
        self.callback = None
        self.rede.registrar_recebedor(self._rdt_rcv)

    def registrar_monitor_de_conexoes_aceitas(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que uma nova conexão for aceita
        """
        self.callback = callback

    def _rdt_rcv(self, src_addr, dst_addr, segment):
        src_port, dst_port, seq_no, ack_no, \
            flags, window_size, checksum, urg_ptr = read_header(segment)

        if dst_port != self.porta:
            # Ignora segmentos que não são destinados à porta do nosso servidor
            return
        if not self.rede.ignore_checksum and calc_checksum(segment, src_addr, dst_addr) != 0:
            print('descartando segmento com checksum incorreto')
            return

        payload = segment[4*(flags>>12):]
        id_conexao = (src_addr, src_port, dst_addr, dst_port)

        if (flags & FLAGS_SYN) == FLAGS_SYN:
            # A flag SYN estar setada significa que é um cliente tentando estabelecer uma conexão nova
            # Passo 1
            answer_seq = int.from_bytes(os.urandom(4), byteorder="big")  
            conexao = self.conexoes[id_conexao] = Conexao(self, id_conexao, seq_no, answer_seq)
            ack_no = seq_no + 1 
            syn_ack_flags = FLAGS_SYN | FLAGS_ACK
            segment_syn_ack = make_header(dst_port, src_port, answer_seq , ack_no, syn_ack_flags)
            segment_syn_ack = fix_checksum(segment_syn_ack, src_addr, dst_addr)
            self.rede.enviar(segment_syn_ack, src_addr)
            if self.callback:
                self.callback(conexao)
        elif id_conexao in self.conexoes:
            # Passa para a conexão adequada se ela já estiver estabelecida
            self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)
        else:
            print('%s:%d -> %s:%d (pacote associado a conexão desconhecida)' %
                  (src_addr, src_port, dst_addr, dst_port))


class Conexao:
    def __init__(self, servidor, id_conexao, seq_no, answer_seq):
        self.servidor = servidor
        self.id_conexao = id_conexao
        self.seq_no = seq_no # seq do serv 
        self.answer_seq = answer_seq
        self.ack_no = seq_no+1 # seq do cliente + 1 
        self.callback = None
        self.timer = asyncio.get_event_loop().call_later(0, self._timer)  
        self.last_sent_segment = b''
        self.bytes_acknowledged = 0
        self.not_yet_sent = b'' 
        #self.timer.cancel()   # é possível cancelar o timer chamando esse método; esta linha é só um exemplo e pode ser removida
        
        self.estimated_rtt = None
        self.dev_rtt = None 
        self.timeout_interval = 1
        self.timer_start = float()

        self.window = MSS


    def _start_timer(self):
        # print("timer")
        if self.timer:
            self.timer.cancel()
        if self.last_sent_segment:
            self.timer = asyncio.get_event_loop().call_later(self.timeout_interval, self._timer)
            # print(self.timeout_interval)
            



    def _timer(self):
        print("TIMEOUTTT cuh ")
        self.window = max(MSS, self.window // 2) 
        self.bytes_acknowledged = 0
        # print("WE WINDOWS", self.window)
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        ack_segment = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_ACK) + self.last_sent_segment[:self.window]
        ack_segment = fix_checksum(ack_segment, dst_addr, src_addr)
        # print(self.last_sent_segment[:10])
        self.last_sent_segment = self.last_sent_segment[self.window:]
        self.servidor.rede.enviar(ack_segment, src_addr)  



    def _rdt_rcv(self, seq_no, ack_no, flags, payload):
        # Passo 2
        if seq_no != self.ack_no : #expected seq not received  
            print("expected seq not received")
            return


        #passo 7 
        if (flags & FLAGS_ACK) == FLAGS_ACK :
            # apenas se tiver recebido ack inteiro 
            new_bytes = ack_no - self.seq_no
            if new_bytes > 0:
                self.bytes_acknowledged += new_bytes
                print("qnts:", self.bytes_acknowledged)
                if self.bytes_acknowledged//MSS >= self.window//MSS:
                    # print("chego aq")
                    self.window += MSS
                    self.bytes_acknowledged = 0
                    # print(f"we windows {self.window}")

                if self.last_sent_segment:
                    self._start_timer() 
                elif self.timer:
                    self.timer.cancel()  


                if self.not_yet_sent:
                    # self._start_timer() 
                    self.enviar(self.not_yet_sent)


        self.seq_no = ack_no
        # passo 5 e 6 
        # eu n sei oq ta conteceno aq pra fala a vdd, eu so estava brincando e funcionou '-'(provavelmente esta errado)
        if (len(payload) == 0) and ((flags & FLAGS_ACK) == FLAGS_ACK):
            if self.last_sent_segment:
                self._start_timer()
                self.calc_rtt()
                return
            elif ((flags & FLAGS_FIN) != FLAGS_FIN):
                return

        self.ack_no += len(payload) if len(payload) > 0 else 1 # passo 4 
        
        if self.callback:
            self.callback(self, payload)

        #pkt vazio com ACK 
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        ack_segment = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_ACK) #header + vazio
        ack_segment = fix_checksum(ack_segment, dst_addr, src_addr)
        self.servidor.rede.enviar(ack_segment, dst_addr) 

        if (flags & FLAGS_FIN) == FLAGS_FIN:
            del self.servidor.conexoes[self.id_conexao]


    # Os métodos abaixo fazem parte da API
    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    def enviar(self, dados):
        """
        Usado pela camada de aplicação para enviar dados
        """
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        self.last_sent_segment = b''
        bytes_to_send = min(len(dados), self.window)
        bytes_sent = 0

        for i in range(0, bytes_to_send, MSS):
            # print("iteration ", i)
            # min_range = min(i+MSS, self.window)
            dados_parsed = dados[i:i+MSS]
            print(i, self.window)
            print(dados_parsed[:10])
            self.last_sent_segment += dados_parsed
            # print(i/MSS , self.window/MSS)
            # print(i//MSS, self.window//MSS)
            # Cria um segmento com o número de sequência atual e o número de reconhecimento atual\
            if i//MSS >= self.window//MSS:
                print("huh?")
                break
            segmento = make_header(dst_port, src_port, self.answer_seq+1, self.ack_no, FLAGS_ACK) + dados_parsed
            self.answer_seq += len(dados_parsed) 
            segmento = fix_checksum(segmento, dst_addr, src_addr)
            self.servidor.rede.enviar(segmento, dst_addr)
            bytes_sent += len(dados_parsed)
            # print("chego", dados[-10:])
    
        self.not_yet_sent = dados[bytes_sent:]
        self.timer_start = time.time() # passo 6 
        self._start_timer()
            


    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        # Passo 4
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        fin_segment = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_FIN) #header + vazio
        fin_segment = fix_checksum(fin_segment, dst_addr, src_addr)
        self.servidor.rede.enviar(fin_segment, dst_addr)     
        
        # TODO: implemente aqui o fechamento de conexão
        pass

    def calc_rtt(self):
        #passo 6 
        # print("hererererere", self.ack_no, self.answer_seq, self.seq_no, self.ack_times)
        sample_rtt = time.time() - self.timer_start
        # print(sample_rtt)
        if self.estimated_rtt is None: # primeiro sample_rtt 
            self.estimated_rtt = sample_rtt 
            self.dev_rtt = sample_rtt / 2
        else: # recalcular baseado nas equacoes do livro 
            alpha = 0.125
            beta = 0.25
            self.estimated_rtt = ((1 - alpha) * self.estimated_rtt ) + ( alpha * sample_rtt)
            self.dev_rtt =( (1 - beta) * self.dev_rtt) + (beta * abs(sample_rtt - self.estimated_rtt))

        self.timeout_interval = self.estimated_rtt + (4 * self.dev_rtt)
        # print(f"timeout_interval: {self.timeout_interval:.2f}, estimated_rtt: {self.estimated_rtt:.2f}, dev_rtt: {self.dev_rtt:.2f}")
        
