#!/bin/sh
# Swarm installer - curl -fsSL https://raw.githubusercontent.com/mtomcal/swarm/main/setup.sh | sh
set -e

REPO="https://raw.githubusercontent.com/mtomcal/swarm/main"
INSTALL_DIR="${SWARM_INSTALL_DIR:-$HOME/.local/bin}"
BINARY_NAME="swarm"

main() {
    echo "Installing swarm..."

    # Create install directory if needed
    if [ ! -d "$INSTALL_DIR" ]; then
        mkdir -p "$INSTALL_DIR"
        echo "Created $INSTALL_DIR"
    fi

    # Download swarm.py
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$REPO/swarm.py" -o "$INSTALL_DIR/$BINARY_NAME"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$INSTALL_DIR/$BINARY_NAME" "$REPO/swarm.py"
    else
        echo "Error: curl or wget required" >&2
        exit 1
    fi

    chmod +x "$INSTALL_DIR/$BINARY_NAME"

    # Check PATH
    case ":$PATH:" in
        *":$INSTALL_DIR:"*) ;;
        *)
            echo ""
            echo "Add to your shell profile:"
            echo "  export PATH=\"\$PATH:$INSTALL_DIR\""
            ;;
    esac

    echo ""
    echo "Installed: $INSTALL_DIR/$BINARY_NAME"
    echo "Run 'swarm --help' to get started"
}

main
