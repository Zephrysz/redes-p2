import asyncio
import os 
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
            answer_seq = int.from_bytes(os.urandom(2), byteorder="big")  
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
        self.timer = asyncio.get_event_loop().call_later(1, self._exemplo_timer)  # um timer pode ser criado assim; esta linha é só um exemplo e pode ser removida
        #self.timer.cancel()   # é possível cancelar o timer chamando esse método; esta linha é só um exemplo e pode ser removida

    def _exemplo_timer(self):
        # Esta função é só um exemplo e pode ser removida
        print('Este é um exemplo de como fazer um timer')

    def _rdt_rcv(self, seq_no, ack_no, flags, payload):
        # print("chega aq?")
        # Passo 2
        if seq_no != self.ack_no : #expected seq not received  
            return

        if (len(payload) == 0) and ((flags & FLAGS_ACK) == FLAGS_ACK):
            # print("pra n responde ACK com ACK sla ")
            return
        if self.callback:
            self.callback(self, payload)
        self.ack_no += len(payload)
        self.seq_no = ack_no


        #pkt vazio 
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        ack_segment = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_ACK) #header + vazio
        ack_segment = fix_checksum(ack_segment, dst_addr, src_addr)
        self.servidor.rede.enviar(ack_segment, src_addr)


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
        for i in range(0, len(dados), MSS):
            dados_parsed = dados[i:i+MSS]
            # Cria um segmento com o número de sequência atual e o número de reconhecimento atual\
            segmento = make_header(dst_port, src_port, self.answer_seq+1, self.ack_no, FLAGS_ACK) + dados_parsed
            segmento = fix_checksum(segmento, dst_addr, src_addr)
            # print("chego", dados[:10])
            self.servidor.rede.enviar(segmento, dst_addr)
            self.answer_seq += len(dados_parsed) 


        # TODO: implemente aqui o envio de dados.
        # Chame self.servidor.rede.enviar(segmento, dest_addr) para enviar o segmento
        # que você construir para a camada de rede.
        pass

    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        # TODO: implemente aqui o fechamento de conexão
        pass
