import sys
import os

# Localizar diretório da aplicação — funciona como script E como .exe compilado
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

import argparse
p = argparse.ArgumentParser()
p.add_argument("--cron", action="store_true")
p.add_argument("--agendado", action="store_true")
args, _ = p.parse_known_args()

if args.agendado:
    import main as core_main
    core_main.run_agendado()
elif args.cron:
    import main as core_main
    sys.argv = ["main.py", "--mode", "2", "--output_mode", "completo"]
    core_main.main()
else:
    from gui import ExtratorApp
    ExtratorApp().mainloop()
