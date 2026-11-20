#!/bin/sh
# ForgeHub: executar localmente com sudo sh diagnose_ssh.sh
# Somente leitura: nao altera servicos, contas, firewall ou arquivos.
# Nao usa set -e: cada consulta indisponivel deve permitir concluir o relatorio.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
echo 'FORGEHUB_SSH_DIAGNOSTIC_V1 Linux'
echo '--- Ambiente ---'
hostname 2>/dev/null || echo 'NAO_VERIFICADO: hostname.'
uid=$(id -u 2>/dev/null)
if [ "$uid" = 0 ]; then echo 'Root: sim'; else echo 'Root: nao ou NAO_VERIFICADO; algumas consultas exigem sudo.'; fi

echo '--- Servidor SSH ---'
sshd_bin=$(command -v sshd 2>/dev/null)
if [ -z "$sshd_bin" ] && [ -x /usr/sbin/sshd ]; then sshd_bin=/usr/sbin/sshd; fi
if [ -n "$sshd_bin" ]; then
    echo "Executavel sshd: $sshd_bin"
    if [ "$uid" = 0 ]; then
        if "$sshd_bin" -t >/dev/null 2>&1; then echo 'Configuracao padrao sshd: valida (-t).';
        else echo 'FALHA: sshd -t (configuracao invalida, chaves do host ausentes ou outro requisito local).'; fi
    else echo 'NAO_VERIFICADO: sshd -t exige root para ler as chaves do host.'; fi
else echo 'AUSENTE no PATH e /usr/sbin: servidor SSH. Instalar openssh-server pode ser necessario.'; fi
if command -v systemctl >/dev/null 2>&1; then
    for unit in ssh.service sshd.service ssh.socket sshd.socket tailscaled.service; do
        echo "Unidade: $unit"
        systemctl show "$unit" --no-pager -p LoadState -p ActiveState -p SubState -p UnitFileState 2>/dev/null ||
            echo 'NAO_VERIFICADO: estado da unidade.'
    done
else echo 'NAO_VERIFICADO: systemd indisponivel; verificar o gerenciador de servicos desta distribuicao.'; fi

echo '--- Portas TCP em escuta (sem processos/argumentos) ---'
if command -v ss >/dev/null 2>&1; then ss -ltnH 2>/dev/null || echo 'NAO_VERIFICADO: listeners.'
else echo 'NAO_VERIFICADO: ferramenta ss ausente.'; fi

echo '--- Tailscale local ---'
if command -v tailscale >/dev/null 2>&1; then echo 'Cliente Tailscale encontrado.';
else echo 'AUSENTE: cliente Tailscale no PATH.'; fi
if command -v ip >/dev/null 2>&1; then ip -brief address show dev tailscale0 2>/dev/null || echo 'NAO_VERIFICADO: interface tailscale0.'
else echo 'NAO_VERIFICADO: ferramenta ip ausente.'; fi

echo '--- Conta darckware ---'
if id darckware >/dev/null 2>&1; then
    echo 'Conta darckware encontrada.'
    id darckware 2>/dev/null || echo 'NAO_VERIFICADO: grupos da conta.'
    if command -v passwd >/dev/null 2>&1; then
        passwd -S darckware 2>/dev/null || echo 'NAO_VERIFICADO: estado da senha (L=travada, P=definida, NP=sem senha).'
    else echo 'NAO_VERIFICADO: passwd indisponivel para consultar bloqueio da conta.'; fi
    if command -v chage >/dev/null 2>&1; then
        chage -l darckware 2>/dev/null || echo 'NAO_VERIFICADO: expiracao da conta (chage).'
    fi
    if command -v faillock >/dev/null 2>&1; then
        faillock --user darckware 2>/dev/null | head -n 5 || true
    fi
    if command -v getent >/dev/null 2>&1 && command -v cut >/dev/null 2>&1; then
        account=$(getent passwd darckware 2>/dev/null)
        home_dir=$(printf '%s\n' "$account" | cut -d: -f6)
        login_shell=$(printf '%s\n' "$account" | cut -d: -f7)
        echo "Shell: $login_shell"
        case "$home_dir" in
            /*) for file in "$home_dir" "$home_dir/.ssh" "$home_dir/.ssh/authorized_keys"; do
                if [ -e "$file" ]; then stat -c '%n | modo=%a | dono=%U:%G | bytes=%s' -- "$file" 2>/dev/null || echo 'NAO_VERIFICADO: metadados.';
                else echo "AUSENTE ou sem permissao para consultar: $file"; fi
            done ;;
            *) echo 'NAO_VERIFICADO: diretorio da conta nao retornou um caminho absoluto.' ;;
        esac
    else echo 'NAO_VERIFICADO: diretorio e shell da conta (getent/cut ausentes).'; fi
else echo 'AUSENTE ou NAO_VERIFICADO: conta darckware (consulta id falhou).'; fi

echo '--- Configuracao efetiva SSH (diretivas selecionadas) ---'
if [ "$uid" = 0 ] && [ -n "$sshd_bin" ] && command -v awk >/dev/null 2>&1; then
    "$sshd_bin" -T -C user=darckware,host=localhost,addr=127.0.0.1 2>/dev/null |
        awk 'tolower($1) ~ /^(port|pubkeyauthentication|passwordauthentication|strictmodes|usepam|allowusers|allowgroups|denyusers|denygroups|authorizedkeysfile)$/' ||
        echo 'NAO_VERIFICADO: sshd -T.'
elif [ -r /etc/ssh/sshd_config ] && command -v awk >/dev/null 2>&1; then
    awk 'tolower($1)=="port" && $2 ~ /^[0-9]+$/ {print "Port", $2}
         tolower($1) ~ /^(pubkeyauthentication|passwordauthentication|strictmodes|usepam)$/ && $2 ~ /^(yes|no)$/ {print $1, $2}
         tolower($1) ~ /^(allowusers|allowgroups|denyusers|denygroups|authorizedkeysfile)$/ {print $0}
         tolower($1)=="include" {print "Include presente: configuracao adicional nao avaliada"}
         tolower($1)=="match" {print "Match presente: regras condicionais nao avaliadas"}' /etc/ssh/sshd_config 2>/dev/null || echo 'NAO_VERIFICADO: configuracao.'
else echo 'NAO_VERIFICADO: arquivo padrao ausente/sem leitura ou awk ausente.'; fi

echo '--- Restricoes PAM / acesso SSH ---'
if [ -r /etc/pam.d/sshd ]; then
    grep -E 'pam_access' /etc/pam.d/sshd 2>/dev/null || echo 'Sem pam_access em /etc/pam.d/sshd.'
fi
for acc in /etc/security/access-sshd.conf /etc/security/access.conf; do
    if [ -r "$acc" ]; then
        lines=$(grep -vE '^[[:space:]]*(#|$)' "$acc" 2>/dev/null)
        if [ -n "$lines" ]; then
            echo "Regras ativas em $acc:"
            printf '%s\n' "$lines" | head -n 20
        fi
    fi
done
if command -v ucr >/dev/null 2>&1; then
    echo "UCS auth/sshd/restrict: $(ucr get auth/sshd/restrict 2>/dev/null || echo NAO_VERIFICADO)"
    echo "UCS auth/sshd/user/darckware: $(ucr get auth/sshd/user/darckware 2>/dev/null || echo nao_definido)"
fi

echo '--- Firewall (consulta parcial; regras externas e tailnet nao avaliadas) ---'
if command -v ufw >/dev/null 2>&1; then ufw status 2>/dev/null || echo 'NAO_VERIFICADO: ufw.'
else echo 'NAO_VERIFICADO: ufw ausente.'; fi
if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --state 2>/dev/null || echo 'NAO_VERIFICADO: firewalld.'
    firewall-cmd --list-services 2>/dev/null || echo 'NAO_VERIFICADO: servicos da zona padrao do firewalld.'
    firewall-cmd --list-ports 2>/dev/null || echo 'NAO_VERIFICADO: portas da zona padrao do firewalld.'
else echo 'NAO_VERIFICADO: firewalld ausente.'; fi
echo 'Nao exibe chaves ou senhas e nao le logs de autenticacao. Nao testa o login nem a chave pendente do ForgeHub.'
echo 'FIM_DO_DIAGNOSTICO'
