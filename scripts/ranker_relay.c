/*
 * ranker_relay.c — Tiny Unix-socket relay for Lua ↔ Python ranker.
 *
 * Replaces the Python rancker_client.py for ~2ms startup instead of ~80ms.
 * Reads JSON request from stdin, connects to the Unix socket, sends the
 * request, and writes the response to stdout.  In async mode (--async),
 * sends only and exits without waiting.
 *
 * Build:  cc -O2 -o ranker_relay ranker_relay.c
 * Usage:  ranker_relay <socket_path> [--async] < request.json
 */

#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#define TIMEOUT      3
#define MAX_REQUEST  (64 * 1024)
#define MAX_RESPONSE (64 * 1024)

static void on_timeout(int sig) { _exit(1); }

int main(int argc, char *argv[]) {
    signal(SIGALRM, on_timeout);
    alarm(TIMEOUT);

    if (argc < 2) {
        fprintf(stderr, "Usage: %s <socket_path> [--async]\n", argv[0]);
        return 1;
    }

    const char *sock_path = argv[1];
    int async_mode = (argc >= 3 && strcmp(argv[2], "--async") == 0);

    /* Read entire stdin into buffer */
    static char request[MAX_REQUEST];
    size_t req_len = fread(request, 1, MAX_REQUEST - 1, stdin);
    if (req_len == 0) return 1;
    request[req_len] = '\0';

    /* Unix socket connect */
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return 1;

    struct timeval tv = {2, 0};
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, sock_path, sizeof(addr.sun_path) - 1);

    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(fd);
        return 1;
    }

    /* Send request + newline */
    ssize_t sent = 0;
    while (sent < (ssize_t)req_len) {
        ssize_t n = write(fd, request + sent, req_len - sent);
        if (n <= 0) { close(fd); return 1; }
        sent += n;
    }
    if (write(fd, "\n", 1) != 1) { close(fd); return 1; }

    if (async_mode) {
        close(fd);
        return 0;
    }

    /* Read response until newline or EOF */
    static char response[MAX_RESPONSE];
    ssize_t total = 0;
    while (total < MAX_RESPONSE - 1) {
        ssize_t n = read(fd, response + total, MAX_RESPONSE - 1 - total);
        if (n <= 0) break;
        total += n;
        if (response[total - 1] == '\n') break;
    }
    response[total] = '\0';

    close(fd);
    write(STDOUT_FILENO, response, total);
    return 0;
}
