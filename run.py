from __future__ import annotations

import webbrowser

from werkzeug.serving import make_server

from app.web import create_app


HOST = "127.0.0.1"
PORT = 8766
URL = f"http://{HOST}:{PORT}"


def main(app_factory=create_app, server_factory=make_server, browser_open=webbrowser.open) -> int:
    app = app_factory()
    server = server_factory(HOST, PORT, app, threaded=True)
    print(f"[DECIP] Servidor pronto em {URL}")
    try:
        browser_open(URL)
    except Exception as exc:
        print(f"[AVISO] Não foi possível abrir o navegador automaticamente ({type(exc).__name__}).")
        print(f"[DECIP] Abra manualmente: {URL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[DECIP] Encerrando o servidor...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

