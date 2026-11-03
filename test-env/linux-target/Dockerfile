FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-server && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/sh darckware && passwd -d darckware \
    && mkdir -p /run/sshd /etc/ssh/authorized_keys \
    && printf '\nPasswordAuthentication no\nPermitRootLogin no\nAuthorizedKeysFile /etc/ssh/authorized_keys/%%u\n' >> /etc/ssh/sshd_config
CMD ["/usr/sbin/sshd", "-D", "-e"]
