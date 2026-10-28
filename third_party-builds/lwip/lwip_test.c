/* lwIP self-test on the simulator: TCP and UDP over the loopback
 * interface with NO_SYS, plus the Ethernet path (ARP, DHCP, httpd, SNTP,
 * TFTP) brought up on a dummy interface so that they are linked and
 * their start-up code runs.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdio.h>
#include <string.h>

#include "lwip/init.h"
#include "lwip/netif.h"
#include "lwip/tcp.h"
#include "lwip/udp.h"
#include "lwip/dhcp.h"
#include "lwip/dns.h"
#include "lwip/etharp.h"
#include "lwip/timeouts.h"
#include "lwip/inet_chksum.h"
#include "lwip/apps/httpd.h"
#include "lwip/apps/sntp.h"
#include "lwip/apps/tftp_server.h"
#include "netif/ethernet.h"

static u32_t now_ms;
u32_t sys_now(void) { return now_ms; }

static u32_t rand_state = 12345;
unsigned int mipsx_lwip_rand(void)
{
  rand_state = rand_state * 1103515245u + 12345u;
  return rand_state >> 8;
}

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static void run(int ms)
{
  for (int i = 0; i < ms; i++) {
    now_ms++;
    netif_poll_all();
    sys_check_timeouts();
  }
}

/* TCP echo server and a client that sends a pattern and checks the echo. */
#define TCP_LEN 20000
static unsigned char tx_pattern[TCP_LEN];
static unsigned rx_count, tx_sent, rx_bad;
static int client_connected, server_closed;

static err_t srv_recv(void *arg, struct tcp_pcb *pcb, struct pbuf *p, err_t err)
{
  (void)arg; (void)err;
  if (!p) {
    server_closed = 1;
    tcp_close(pcb);
    return ERR_OK;
  }
  for (struct pbuf *q = p; q; q = q->next)
    tcp_write(pcb, q->payload, q->len, TCP_WRITE_FLAG_COPY);
  tcp_output(pcb);
  tcp_recved(pcb, p->tot_len);
  pbuf_free(p);
  return ERR_OK;
}

static err_t srv_accept(void *arg, struct tcp_pcb *pcb, err_t err)
{
  (void)arg; (void)err;
  tcp_recv(pcb, srv_recv);
  return ERR_OK;
}

static void cli_send(struct tcp_pcb *pcb)
{
  while (tx_sent < TCP_LEN) {
    u16_t n = tcp_sndbuf(pcb);
    if (n == 0)
      break;
    if (n > TCP_LEN - tx_sent)
      n = TCP_LEN - tx_sent;
    if (n > 1000)
      n = 1000;
    if (tcp_write(pcb, tx_pattern + tx_sent, n, 0) != ERR_OK)
      break;
    tx_sent += n;
  }
  tcp_output(pcb);
}

static err_t cli_sent(void *arg, struct tcp_pcb *pcb, u16_t len)
{
  (void)arg; (void)len;
  cli_send(pcb);
  return ERR_OK;
}

static err_t cli_recv(void *arg, struct tcp_pcb *pcb, struct pbuf *p, err_t err)
{
  (void)arg; (void)err;
  if (!p)
    return ERR_OK;
  for (struct pbuf *q = p; q; q = q->next) {
    const unsigned char *b = q->payload;
    for (u16_t i = 0; i < q->len; i++, rx_count++)
      if (rx_count >= TCP_LEN || b[i] != tx_pattern[rx_count])
        rx_bad++;
  }
  tcp_recved(pcb, p->tot_len);
  pbuf_free(p);
  if (rx_count == TCP_LEN)
    tcp_close(pcb);
  return ERR_OK;
}

static err_t cli_connected(void *arg, struct tcp_pcb *pcb, err_t err)
{
  (void)arg;
  client_connected = err == ERR_OK;
  tcp_recv(pcb, cli_recv);
  tcp_sent(pcb, cli_sent);
  cli_send(pcb);
  return ERR_OK;
}

static void test_tcp(void)
{
  for (unsigned i = 0; i < TCP_LEN; i++)
    tx_pattern[i] = (unsigned char)(i * 7 + (i >> 8));

  struct tcp_pcb *l = tcp_new();
  CHECK(l != NULL);
  CHECK(tcp_bind(l, IP_ADDR_ANY, 7) == ERR_OK);
  l = tcp_listen(l);
  CHECK(l != NULL);
  tcp_accept(l, srv_accept);

  struct tcp_pcb *c = tcp_new();
  ip_addr_t lo;
  IP_ADDR4(&lo, 127, 0, 0, 1);
  CHECK(tcp_connect(c, &lo, 7, cli_connected) == ERR_OK);
  run(2000);
  CHECK(client_connected);
  CHECK(tx_sent == TCP_LEN);
  CHECK(rx_count == TCP_LEN);
  CHECK(rx_bad == 0);
  CHECK(server_closed);
  tcp_close(l);
  printf("tcp: sent %u, echoed %u, bad %u\n", tx_sent, rx_count, rx_bad);
}

/* UDP: send datagrams of several sizes (including fragmented ones) to
 * ourselves. */
static unsigned udp_rx, udp_rx_bytes, udp_bad;

static void udp_rx_cb(void *arg, struct udp_pcb *pcb, struct pbuf *p,
                      const ip_addr_t *addr, u16_t port)
{
  (void)arg; (void)pcb; (void)addr; (void)port;
  unsigned char buf[4000];
  u16_t n = pbuf_copy_partial(p, buf, sizeof buf, 0);
  for (u16_t i = 0; i < n; i++)
    if (buf[i] != (unsigned char)(i ^ n))
      udp_bad++;
  udp_rx++;
  udp_rx_bytes += n;
  pbuf_free(p);
}

static void test_udp(void)
{
  static const u16_t sizes[] = { 1, 100, 1472, 1473, 3000 };
  struct udp_pcb *r = udp_new(), *s = udp_new();
  ip_addr_t lo;
  IP_ADDR4(&lo, 127, 0, 0, 1);
  CHECK(udp_bind(r, IP_ADDR_ANY, 5000) == ERR_OK);
  udp_recv(r, udp_rx_cb, NULL);
  unsigned total = 0;
  for (unsigned k = 0; k < sizeof sizes / sizeof sizes[0]; k++) {
    u16_t n = sizes[k];
    struct pbuf *p = pbuf_alloc(PBUF_TRANSPORT, n, PBUF_RAM);
    CHECK(p != NULL);
    for (u16_t i = 0; i < n; i++)
      ((unsigned char *)p->payload)[i] = (unsigned char)(i ^ n);
    CHECK(udp_sendto(s, p, &lo, 5000) == ERR_OK);
    pbuf_free(p);
    total += n;
    run(10);
  }
  CHECK(udp_rx == sizeof sizes / sizeof sizes[0]);
  CHECK(udp_rx_bytes == total);
  CHECK(udp_bad == 0);
  udp_remove(r);
  udp_remove(s);
  printf("udp: %u datagrams, %u bytes, bad %u\n", udp_rx, udp_rx_bytes, udp_bad);
}

/* A dummy Ethernet interface that counts the frames lwIP sends. */
static unsigned eth_tx_frames;
static struct netif eth;

static err_t eth_output(struct netif *netif, struct pbuf *p)
{
  (void)netif;
  /* Check the IP header checksum of IPv4 frames. */
  unsigned char hdr[34];
  if (pbuf_copy_partial(p, hdr, sizeof hdr, 0) == sizeof hdr &&
      hdr[12] == 0x08 && hdr[13] == 0x00)
    CHECK(inet_chksum(hdr + 14, 20) == 0);
  eth_tx_frames++;
  return ERR_OK;
}

static err_t eth_init(struct netif *netif)
{
  static const u8_t mac[6] = { 0x02, 0x00, 0x5e, 0x00, 0x00, 0x01 };
  netif->name[0] = 'e';
  netif->name[1] = 'n';
  netif->output = etharp_output;
  netif->linkoutput = eth_output;
  netif->mtu = 1500;
  netif->hwaddr_len = 6;
  memcpy(netif->hwaddr, mac, 6);
  netif->flags = NETIF_FLAG_BROADCAST | NETIF_FLAG_ETHARP | NETIF_FLAG_ETHERNET;
  return ERR_OK;
}

static void *tftp_open(const char *name, const char *mode, u8_t write)
{
  (void)name; (void)mode; (void)write;
  return NULL;
}
static void tftp_close(void *h) { (void)h; }
static int tftp_read(void *h, void *buf, int n) { (void)h; (void)buf; (void)n; return -1; }
static int tftp_write(void *h, struct pbuf *p) { (void)h; (void)p; return -1; }
static const struct tftp_context tftp_ctx = { tftp_open, tftp_close, tftp_read, tftp_write, NULL };

static void test_eth(void)
{
  CHECK(netif_add(&eth, NULL, NULL, NULL, NULL, eth_init, ethernet_input) != NULL);
  netif_set_hostname(&eth, "spa3000");
  netif_set_default(&eth);
  netif_set_up(&eth);
  netif_set_link_up(&eth);
  CHECK(dhcp_start(&eth) == ERR_OK);
  httpd_init();
  tftp_init_server(&tftp_ctx);
  sntp_setoperatingmode(SNTP_OPMODE_POLL);
  sntp_setservername(0, "pool.ntp.org");
  sntp_init();
  run(10000);
  /* DHCP discovers have gone out (no server answers). */
  CHECK(eth_tx_frames >= 2);
  printf("eth: %u frames sent\n", eth_tx_frames);
}

int main(void)
{
  lwip_init();
  test_tcp();
  test_udp();
  test_eth();
  printf(failures ? "lwip_test: FAIL (%d)\n" : "lwip_test: PASS\n", failures);
  return failures != 0;
}
