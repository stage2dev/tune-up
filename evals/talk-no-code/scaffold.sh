#!/bin/sh
cat > app.py <<'PY'
def soma(a, b):
    return a + b


def soma(a, b):
    return a - b


def main():
    print(soma(2, 3))


if __name__ == "__main__":
    main()
PY
