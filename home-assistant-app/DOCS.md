# Health OS Home Assistant app

After installation, start Health OS and select **Open Web UI**. Home Assistant Ingress signs you in
automatically. On first use, confirm your browser-detected timezone and personal baselines.

Every Home Assistant user receives an independent Health OS account. Existing standalone PIN
accounts are not automatically matched or merged. An Ingress-created user may optionally enable
standalone PIN access later in Health OS settings.

Health OS stores its database and generated session key in the app's writable `/data` directory.
The app exposes no direct host port. Home Assistant identity headers are accepted only from the
Supervisor Ingress proxy at `172.30.32.2`.
