#!/bin/bash
set -e

# === Проверка поддержки терминала ===
if [ -z "$TERM" ] || [ "$TERM" = "dumb" ]; then
    echo "Your terminal does not support color formatting. Using basic mode."
    BLUE=""
    CYAN=""
    GREEN=""
    RED=""
    YELLOW=""
    PURPLE=""
    RESET=""
    BOLD=""
else
    BLUE="\033[34m"
    CYAN="\033[36m"
    GREEN="\033[32m"
    RED="\033[31m"
    YELLOW="\033[33m"
    PURPLE="\033[35m"
    RESET="\033[0m"
    BOLD="\033[1m"
fi

center_title() {
    local title="$1"
    local title_length=${#title}
    local width=$(tput cols 2>/dev/null || echo 50)
    [ $width -lt $((title_length + 4)) ] && width=$((title_length + 4))
    local padding=$(( (width - title_length) / 2 ))
    local left_padding=$(printf "%${padding}s" | tr ' ' '-')
    local right_padding=$(printf "%${padding}s" | tr ' ' '-')
    [ $(( (width - title_length) % 2 )) -ne 0 ] && right_padding="${right_padding}-"
    echo "${left_padding}${title}${right_padding}"
}

spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

LOG_DIR="Pust"
LOG_FILE="$LOG_DIR/Pust_installer.log"
apt install curl
mkdir -p "$LOG_DIR"

while true; do
    clear
    echo -e "${PURPLE}${BOLD}"
    curl -s https://raw.githubusercontent.com/C0dwiz/Pust/refs/heads/dev-test/assets/download.txt   
    echo -e "${RESET}"
    echo -e "${CYAN}${BOLD}$(center_title 'Menu')${RESET}"
    echo -e "${BLUE}1. Install Pust${RESET}"
    echo -e "${BLUE}2. Install Pust in venv${RESET}"
    echo -e "${BLUE}3. Install Pust in Docker${RESET}"
    echo -e "${BLUE}4. Remove Pust${RESET}"
    echo -e "${BLUE}0. Exit${RESET}"
    echo -e "${CYAN}$(center_title '')${RESET}"
    read -p $'\033[33m> \033[0m ' choice

    case $choice in
        1)
            echo -e "${GREEN}Installing Pust...${RESET}"
            (apt-get update && apt-get install -y git python3 python3-pip) &>> "$LOG_FILE" & spinner $!
            if [ -d "Pust" ]; then
                echo -e "${YELLOW}Pust directory already exists. Skipping clone.${RESET}"
            else
                git clone https://github.com/C0dwiz/Pust &>> "$LOG_FILE" & spinner $!
            fi
            cd Pust
            pip3 install -r requirements.txt &>> "$LOG_FILE" & spinner $!
            python3 -m Pust &>> "$LOG_FILE" & spinner $!
            echo -e "${GREEN}Completed successfully!${RESET}"
            read -p $'\033[33mPress Enter to continue... \033[0m'
            cd ..
            ;;
        2)
            echo -e "${GREEN}Installing Pust in venv...${RESET}"
            (apt-get update && apt-get install -y git python3 python3-pip python3-venv) &>> "$LOG_FILE" & spinner $!
            if [ -d "Pust" ]; then
                echo -e "${YELLOW}Pust directory already exists. Skipping clone.${RESET}"
            else
                git clone https://github.com/C0dwiz/Pust &>> "$LOG_FILE" & spinner $!
            fi
            cd Pust
            python3 -m venv Pust_UB
            source Pust_UB/bin/activate
            pip install -r requirements.txt &>> "$LOG_FILE" & spinner $!
            python3 -m Pust &>> "$LOG_FILE" & spinner $!
            echo -e "${GREEN}Completed successfully!${RESET}"
            read -p $'\033[33mPress Enter to continue... \033[0m'
            cd ..
            ;;
        3)
            echo -e "${GREEN}Installing Pust in Docker...${RESET}"
            (apt-get update && apt-get install curl -y) &>> "$LOG_FILE" & spinner $!
            bash <(curl -s https://raw.githubusercontent.com/C0dwiz/Pust/refs/heads/master/docker.sh) &>> "$LOG_FILE" & spinner $!
            echo -e "${GREEN}Completed successfully!${RESET}"
            read -p $'\033[33mPress Enter to continue... \033[0m'
            ;;
        4)
            echo -e "${RED}Removing Pust...${RESET}"
            rm -rf Pust &>> "$LOG_FILE"
            docker stop Pust_ub &>> "$LOG_FILE" || true
            docker rm -f Pust_ub &>> "$LOG_FILE" || true
            echo -e "${GREEN}Completed successfully!${RESET}"
            read -p $'\033[33mPress Enter to continue... \033[0m'
            ;;
        0)
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice!${RESET}"
            read -p $'\033[33mPress Enter to continue... \033[0m'
            ;;
    esac
done
