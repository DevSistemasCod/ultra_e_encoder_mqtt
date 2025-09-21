import network
from umqtt.simple import MQTTClient
from machine import Pin, time_pulse_us
from time import sleep
import ujson

# ======== CONFIGURAÇÕES ========
REDE_SSID = "WIFI_IOT_CFP601"
REDE_SENHA = "iot@senai601"

BROKER_MQTT = "broker.hivemq.com"
PORTA_MQTT = 1883
TOPICO_ULTRASSONICO = "sensor/contador/ultrassonico"
TOPICO_ENCODER = "sensor/contador/encoder"
ID_CLIENTE_MQTT = "esp32-combina_ultra_encoder"

# Pinos do sensor ultrassônico
PIN_TRIG = 33
PIN_ECHO = 32

# Pinos do encoder KY-040
PIN_CLK = 25
PIN_DT = 26
PIN_SW = 27

# Constantes do processo
DISTANCIA_DETECCAO_CM = 10
VELOCIDADE_SOM_CM_US = 0.0343
POSICAO_ALVO = 10


# ======== Função: Conectar ao Wi-Fi ========
def conectar_wifi():
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    if not wifi.isconnected():
        print("Conectando ao Wi-Fi...")
        wifi.connect(REDE_SSID, REDE_SENHA)
        while not wifi.isconnected():
            print(".", end="")
            sleep(0.5)
    print("\nConectado ao Wi-Fi! IP:", wifi.ifconfig()[0])


# ======== Função: Conectar ao Broker MQTT ========
def conectar_mqtt():
    cliente = MQTTClient(ID_CLIENTE_MQTT, BROKER_MQTT, port=PORTA_MQTT)
    while True:
        try:
            cliente.connect()
            print("Conectado ao broker MQTT!")
            return cliente
        except Exception as erro:
            print("Erro ao conectar ao MQTT:", erro)
            sleep(2)


# ======== Função: Publicar mensagem no MQTT ========
def publicar_mqtt(cliente, topico, mensagem):
    try:
        cliente.publish(topico, mensagem)
    except Exception as erro:
        print("Erro ao publicar, tentando reconectar...", erro)
        try:
            cliente.connect()
            cliente.publish(topico, mensagem)
            print("Reconectado e publicado com sucesso!")
        except:
            print("Falha ao reconectar ao broker MQTT.")


# ======== Função: Medir distância com ultrassônico ========
def medir_distancia_cm(pino_trig, pino_echo):
    pino_trig.off()
    sleep(0.002)
    pino_trig.on()
    sleep(0.00001)
    pino_trig.off()

    LIMITE_ESPERA_US = 30000
    duracao_pulso = time_pulse_us(pino_echo, 1, LIMITE_ESPERA_US)

    if duracao_pulso < 0:
        return -1

    return (duracao_pulso * VELOCIDADE_SOM_CM_US) / 2


# ======== Função: Monitorar sensor ultrassônico ========
def processar_ultrassonico(cliente, pino_trig, pino_echo, estado_anterior, contadores):
    # Mede a distância em cm usando o sensor ultrassônico
    distancia = medir_distancia_cm(pino_trig, pino_echo)

    # Se houver erro na leitura, retorna sem alterar nada
    if distancia < 0:
        print("Erro na leitura do ultrassônico")
        return estado_anterior, contadores

    # Se a distância for menor ou igual ao limite e o objeto não estava detectado antes
    if distancia <= DISTANCIA_DETECCAO_CM and not estado_anterior:
        # Incrementa cada contador manualmente, de forma clara
        novos_contadores = []
        incrementos = [1, 2, 3]  # valores que serão somados aos contadores

        for indice in range(len(contadores)):
            novo_valor = contadores[indice] + incrementos[indice]
            novos_contadores.append(novo_valor)

        contadores = novos_contadores

        print(f"Contadores atualizados: {contadores}")
        publicar_mqtt(cliente, TOPICO_ULTRASSONICO, ujson.dumps(contadores))
        return True, contadores

    # Se a distância for maior que o limite, o objeto não está mais detectado
    elif distancia > DISTANCIA_DETECCAO_CM:
        return False, contadores

    # Caso contrário, mantém o estado e os contadores sem mudanças
    return estado_anterior, contadores



# ======== Função: Monitorar encoder ========
def processar_encoder(cliente, pino_clk, pino_dt, posicao, contagem, estado_alvo_anterior, clk_anterior):
    clk_atual = pino_clk.value()

    if clk_atual != clk_anterior:
        # Determina direção do giro
        if pino_dt.value() != clk_atual:
            posicao = (posicao + 1) % (POSICAO_ALVO + 1)  # incrementa e aplica o retorno circular
        else:
            posicao = (posicao - 1) % (POSICAO_ALVO + 1)  # decrementa e aplica o retorno circular

        print(f"Posição encoder: {posicao}")

        # Dispara contagem quando atinge a posição alvo
        if posicao == POSICAO_ALVO and not estado_alvo_anterior:
            contagem = contagem + 1
            estado_alvo_anterior = True
            print(f"Encoder atingiu posição alvo! Contagem: {contagem}")
            publicar_mqtt(cliente, TOPICO_ENCODER, str(contagem))
        elif posicao != POSICAO_ALVO:
            estado_alvo_anterior = False

    return posicao, contagem, estado_alvo_anterior, clk_atual


# ======== MAIN ========
def main():
    conectar_wifi()
    cliente_mqtt = conectar_mqtt()

    pino_trig = Pin(PIN_TRIG, Pin.OUT)
    pino_echo = Pin(PIN_ECHO, Pin.IN)
    pino_clk = Pin(PIN_CLK, Pin.IN, Pin.PULL_UP)
    pino_dt = Pin(PIN_DT, Pin.IN, Pin.PULL_UP)
    pino_sw = Pin(PIN_SW, Pin.IN, Pin.PULL_UP)

    # Estados internos (mantidos dentro da main, não como globais)
    contadores = [0, 0, 0]
    peca_detectada = False
    posicao_encoder = 0
    contagem_encoder = 0
    estado_alvo_anterior = False
    clk_anterior = pino_clk.value()

    print("Sistema inicializado! Lendo sensores...")
    sleep(2)

    while True:
        # Processa ultrassônico
        peca_detectada, contadores = processar_ultrassonico(
            cliente_mqtt, pino_trig, pino_echo, peca_detectada, contadores
        )

        # Processa encoder
        posicao_encoder, contagem_encoder, estado_alvo_anterior, clk_anterior = processar_encoder(
            cliente_mqtt, pino_clk, pino_dt, posicao_encoder, contagem_encoder, estado_alvo_anterior, clk_anterior
        )

        sleep(0.01)  # pequeno delay para não sobrecarregar o loop


# ======== Execução Principal ========
if __name__ == "__main__":
    main()

