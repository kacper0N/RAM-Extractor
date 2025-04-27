import sys
import os
import subprocess
import re
import shutil

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QTextEdit, QPushButton, QLabel, QLineEdit,
    QFileDialog, QMessageBox, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal


# ------------------------------ Workers ---------------------------------- #
class RedirectionWorker(QThread):
    output = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, command_str, cwd=None, parent=None):
        super().__init__(parent)
        self.command_str = command_str
        self.cwd = cwd

    def run(self):
        self.output.emit(f"Executing command: {self.command_str}")
        try:
            proc = subprocess.Popen(
                self.command_str,
                shell=True,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            for line in iter(proc.stdout.readline, ""):
                if line:
                    self.output.emit(line.strip())
            proc.stdout.close()
            proc.wait()
            self.output.emit(f"Command finished with code: {proc.returncode}")
        except Exception as e:
            self.output.emit(f"Error while running command: {e}")
        self.finished.emit()


class CommandWorker(QThread):
    output = pyqtSignal(str)
    finished = pyqtSignal(int)  

    def __init__(self, command, cwd=None, parent=None):
        super().__init__(parent)
        self.command = command
        self.cwd = cwd

    def run(self):
        self.output.emit("Running command: " + " ".join(self.command))
        try:
            proc = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            for line in iter(proc.stdout.readline, ""):
                if line:
                    self.output.emit(line.strip())
            proc.stdout.close()
            proc.wait()
            self.output.emit(f"Command finished with code: {proc.returncode}")
            self.finished.emit(proc.returncode)
        except Exception as e:
            self.output.emit(f"Error executing command: {e}")
            self.finished.emit(-1)


class StartupWorker(QThread):
    output = pyqtSignal(str)

    def run(self):
        """Performs all startup‑time installation / build tasks."""
        # Git
        if self.command_exists("git"):
            self.output.emit("Git is installed, skipping installation.")
        else:
            self.output.emit("Git not found, installing git…")
            self.run_command(["sudo", "apt", "install", "-y", "git"])

        # build‑essential
        if self.command_exists("make"):
            self.output.emit("build‑essential is installed, skipping installation.")
        else:
            self.output.emit("build‑essential not found, installing…")
            self.run_command(["sudo", "apt", "install", "-y", "build-essential"])

        # aes/rsakeyfind
        self.output.emit("Installing/updating aeskeyfind…")
        self.run_command(["sudo", "apt", "install", "-y", "aeskeyfind"])
        self.output.emit("Installing/updating rsakeyfind…")
        self.run_command(["sudo", "apt", "install", "-y", "rsakeyfind"])

        # interrogate (serpent/twofish)
        repo = "https://github.com/carmaa/interrogate.git"
        interrogate_dir = "interrogate"
        if not os.path.exists(interrogate_dir):
            self.output.emit("Cloning interrogate…")
            self.run_command(["git", "clone", repo, interrogate_dir])
        else:
            self.output.emit("Updating interrogate…")
            self.run_command(["git", "pull"], cwd=interrogate_dir)
        if os.path.exists(interrogate_dir):
            self.output.emit("Building interrogate…")
            self.run_command(["make"], cwd=interrogate_dir)

        # Zeroize_dump
        repo2 = "https://github.com/kacper0N/Zeroizer.git"
        wyc_dir = "Zeroizer"
        if not os.path.exists(wyc_dir):
            self.output.emit("Cloning Zeroizer…")
            self.run_command(["git", "clone", repo2, wyc_dir])
        else:
            self.output.emit("Updating Zeroizer…")
            self.run_command(["git", "pull"], cwd=wyc_dir)
        if os.path.exists(wyc_dir):
            self.output.emit("Building Zeroizer…")
            self.run_command(["make"], cwd=wyc_dir)

    # -------------------- helpers -------------------- #
    def command_exists(self, cmd: str) -> bool:
        try:
            result = subprocess.run(["which", cmd], capture_output=True, text=True, check=True)
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    def run_command(self, command, cwd=None):
        try:
            proc = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            for line in iter(proc.stdout.readline, ""):
                if line:
                    self.output.emit(line.strip())
            proc.stdout.close()
            proc.wait()
            self.output.emit(f"Command finished with code: {proc.returncode}")
        except Exception as e:
            self.output.emit(f"Error: {e}")


# ------------------------------ Main Window ------------------------------ #
class LauncherWindow(QMainWindow):
    """Main GUI window for RAM‑Extractor."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAM-Extractor")  
        self.resize(950, 650)
        self.initUI()

    # -------------------- UI setup -------------------- #
    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # -------- Left: Console output -------- #
        self.console = QTextEdit(readOnly=True)
        self.console.setLineWrapMode(QTextEdit.NoWrap)
        main_layout.addWidget(self.console, stretch=3)

        # -------- Right: Controls -------- #
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        main_layout.addWidget(control_panel, stretch=1)

        # --- Startup tasks --- #
        control_layout.addWidget(QLabel("Startup Tasks"))
        self.startup_button = QPushButton("Check updates and install tools")
        self.startup_button.clicked.connect(self.start_startup_tasks)
        control_layout.addWidget(self.startup_button)
        control_layout.addSpacing(20)

        # --- Paths: memory + result folder --- #
        control_layout.addWidget(QLabel("Path to memory for analysis:"))
        self.mem_path_edit = QLineEdit()
        control_layout.addWidget(self.mem_path_edit)
        browse_mem_btn = QPushButton("Browse file")
        browse_mem_btn.clicked.connect(self.browse_memory_path)
        control_layout.addWidget(browse_mem_btn)

        control_layout.addWidget(QLabel("Folder for results:"))  
        self.res_path_edit = QLineEdit()
        control_layout.addWidget(self.res_path_edit)
        browse_res_btn = QPushButton("Browse folder")
        browse_res_btn.clicked.connect(self.browse_results_folder)
        control_layout.addWidget(browse_res_btn)
        control_layout.addSpacing(20)

        # --- Tool buttons --- #
        control_layout.addWidget(QLabel("Run tools:"))
        self.aeskey_button = QPushButton("Run aeskeyfind")
        self.aeskey_button.clicked.connect(self.start_aeskeyfind)
        control_layout.addWidget(self.aeskey_button)

        self.rsakey_button = QPushButton("Run rsakeyfind")
        self.rsakey_button.clicked.connect(self.start_rsakeyfind)
        control_layout.addWidget(self.rsakey_button)

        self.serpent_button = QPushButton("Run serpent finder")
        self.serpent_button.clicked.connect(self.start_serpent)
        control_layout.addWidget(self.serpent_button)

        self.twofish_button = QPushButton("Run twofish finder")
        self.twofish_button.clicked.connect(self.start_twofish)
        control_layout.addWidget(self.twofish_button)
        control_layout.addStretch()

        # --- Zeroize section --- #
        control_layout.addSpacing(10)
        control_layout.addWidget(QLabel("Zeroize keys:"))

        self.cb_aes_zero = QCheckBox("AES")      
        self.cb_rsa_zero = QCheckBox("RSA")      
        self.cb_serpent_zero = QCheckBox("Serpent")  
        self.cb_twofish_zero = QCheckBox("Twofish")  

        for cb in (self.cb_aes_zero, self.cb_rsa_zero, self.cb_serpent_zero, self.cb_twofish_zero):
            control_layout.addWidget(cb)

        # Filename for zeroed dump
        control_layout.addWidget(QLabel("Filename for zeroed dump (.mem):"))
        self.zero_filename_edit = QLineEdit()
        self.zero_filename_edit.setPlaceholderText("zero_mem.mem")
        control_layout.addWidget(self.zero_filename_edit)

        self.zero_button = QPushButton("Zero selected keys")
        self.zero_button.clicked.connect(self.start_zeroize_dump)
        control_layout.addWidget(self.zero_button)

    # -------------------- Logging -------------------- #
    def log(self, msg: str):
        """Append a message to the console."""
        self.console.append(msg)

    def separator(self):
        """Insert a blank line to visually separate blocks of output."""
        self.console.append("")

    # -------------------- Common helpers -------------------- #
    def browse_memory_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select memory file")
        if path:
            self.mem_path_edit.setText(path)

    def browse_results_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select results folder")
        if path:
            self.res_path_edit.setText(path)

    # -------------------- Startup tasks -------------------- #
    def start_startup_tasks(self):
        self.startup_button.setEnabled(False)
        self.log("Starting startup tasks…")
        self.startup_worker = StartupWorker()
        self.startup_worker.output.connect(self.log)
        self.startup_worker.finished.connect(lambda: (self.log("Startup tasks completed."), self.startup_button.setEnabled(True)))
        self.startup_worker.start()

    # -------------------- Parsers -------------------- #
    def aes_parser(self, input_path: str, out_path: str):
        try:
            data = re.sub(r"\s+", "", open(input_path, encoding="utf-8").read())
            pattern = r"FOUNDPOSSIBLE(128|256)-BITKEYATBYTE([0-9A-Fa-f]+)KEY"
            pairs = [(m.group(2), m.group(1)) for m in re.finditer(pattern, data)]
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(f"{offset},{size}" for offset, size in pairs))
        except Exception as e:
            self.log(f"Error in aes_parser: {e}")

    def rsa_parser(self, input_path: str, out_path: str):
        try:
            data = re.sub(r"\s+", "", open(input_path, encoding="utf-8").read())
            pattern = r"FOUNDPRIVATEKEYAT([0-9A-Fa-f]+)version"
            offsets = [m.group(1) for m in re.finditer(pattern, data)]
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(f"{off},0" for off in offsets))
        except Exception as e:
            self.log(f"Error in rsa_parser: {e}")

    def twofish_parser(self, input_path: str, out_path: str):
        try:
            data = re.sub(r"\s+", "", open(input_path, encoding="utf-8").read())
            pattern = r"Twofishkeyfoundat([0-9A-Fa-f]+)\."
            offsets = [m.group(1) for m in re.finditer(pattern, data)]
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(f"{off},0" for off in offsets))
        except Exception as e:
            self.log(f"Error in twofish_parser: {e}")

    def serpent_parser(self, input_path: str, out_path: str):
        try:
            data = re.sub(r"\s+", "", open(input_path, encoding="utf-8").read())
            pattern = r"Found\(probable\)SERPENTkeyatoffset([0-9A-Fa-f]+):"
            offsets = [m.group(1) for m in re.finditer(pattern, data)]
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(f"{off},0" for off in offsets))
        except Exception as e:
            self.log(f"Error in serpent_parser: {e}")

    # -------------------- Tool launchers -------------------- #
    def start_aeskeyfind(self):
        self.separator()
        m = self.mem_path_edit.text().strip()
        r = self.res_path_edit.text().strip()
        if not m or not r:
            QMessageBox.critical(self, "Error", "Provide mem file and results folder")
            return
        if not os.path.isfile(m):
            QMessageBox.critical(self, "Error", f"Memory file not found:\n{m}")
            return
        if shutil.which("aeskeyfind") is None:
            QMessageBox.critical(self, "Error", "aeskeyfind not found. Run startup tasks first.")
            return
        os.makedirs(r, exist_ok=True)
        out_txt = os.path.join(r, "aeskeyfind_output.txt")
        cmd = f"aeskeyfind -v -q {m} > {out_txt}"
        self.log("Aeskeyfind is working, please wait…")
        self.log(f"Running aeskeyfind on: {m}")

        self.aes_worker = RedirectionWorker(cmd)
        self.aes_worker.output.connect(self.log)
        self.aes_worker.finished.connect(lambda: self._finish_aes(out_txt, r))
        self.aes_worker.start()

    def _finish_aes(self, out_txt: str, res_dir: str):
        self.log(f"aeskeyfind finished. Output saved to {out_txt}")
        self.aes_parser(out_txt, os.path.join(res_dir, "aes_values.txt"))
        self.log(f"AES values saved to {os.path.join(res_dir, 'aes_values.txt')}")

    def start_rsakeyfind(self):
        self.separator()
        m = self.mem_path_edit.text().strip()
        r = self.res_path_edit.text().strip()
        if not m or not r:
            QMessageBox.critical(self, "Error", "Provide mem file and results folder")
            return
        if not os.path.isfile(m):
            QMessageBox.critical(self, "Error", f"Memory file not found:\n{m}")
            return
        if shutil.which("rsakeyfind") is None:
            QMessageBox.critical(self, "Error", "rsakeyfind not found. Run startup tasks first.")
            return
        os.makedirs(r, exist_ok=True)
        out_txt = os.path.join(r, "rsakeyfind_output.txt")
        cmd = f"rsakeyfind {m} > {out_txt}"
        self.log("Rsakeyfind is working, please wait…")
        self.log(f"Running rsakeyfind on: {m}")

        self.rsa_worker = RedirectionWorker(cmd)
        self.rsa_worker.output.connect(self.log)
        self.rsa_worker.finished.connect(lambda: self._finish_rsa(out_txt, r))
        self.rsa_worker.start()

    def _finish_rsa(self, out_txt: str, res_dir: str):
        self.log(f"rsakeyfind finished. Output saved to {out_txt}")
        self.rsa_parser(out_txt, os.path.join(res_dir, "rsa_values.txt"))
        self.log(f"RSA values saved to {os.path.join(res_dir, 'rsa_values.txt')}")

    def start_serpent(self):
        self.separator()
        m = self.mem_path_edit.text().strip()
        r = self.res_path_edit.text().strip()
        if not m or not r:
            QMessageBox.critical(self, "Error", "Provide mem file and results folder")
            return
        if not os.path.isdir("interrogate"):
            QMessageBox.critical(self, "Error", "interrogate directory not found. Run startup first.")
            return
        os.makedirs(r, exist_ok=True)
        out_txt = os.path.join(r, "serpent_output.txt")
        cmd = f"./interrogate -a serpent {m} > {out_txt}"
        self.log("Serpent finder is working, please wait…")
        self.log(f"Running serpent finder on: {m}")

        self.serpent_worker = RedirectionWorker(cmd, cwd="interrogate")
        self.serpent_worker.output.connect(self.log)
        self.serpent_worker.finished.connect(lambda: self._finish_serpent(out_txt, r))
        self.serpent_worker.start()

    def _finish_serpent(self, out_txt: str, res_dir: str):
        self.log(f"Serpent finder finished. Output saved to {out_txt}")
        self.serpent_parser(out_txt, os.path.join(res_dir, "serpent_values.txt"))
        self.log(f"Serpent values saved to {os.path.join(res_dir, 'serpent_values.txt')}")

    def start_twofish(self):
        self.separator()
        m = self.mem_path_edit.text().strip()
        r = self.res_path_edit.text().strip()
        if not m or not r:
            QMessageBox.critical(self, "Error", "Provide mem file and results folder")
            return
        if not os.path.isdir("interrogate"):
            QMessageBox.critical(self, "Error", "interrogate directory not found. Run startup first.")
            return
        os.makedirs(r, exist_ok=True)
        out_txt = os.path.join(r, "twofish_output.txt")
        cmd = f"./interrogate -a twofish {m} > {out_txt}"
        self.log("Twofish finder is working, please wait…")
        self.log(f"Running twofish finder on: {m}")

        self.twofish_worker = RedirectionWorker(cmd, cwd="interrogate")
        self.twofish_worker.output.connect(self.log)
        self.twofish_worker.finished.connect(lambda: self._finish_twofish(out_txt, r))
        self.twofish_worker.start()

    def _finish_twofish(self, out_txt: str, res_dir: str):
        self.log(f"Twofish finder finished. Output saved to {out_txt}")
        self.twofish_parser(out_txt, os.path.join(res_dir, "twofish_values.txt"))
        self.log(f"Twofish values saved to {os.path.join(res_dir, 'twofish_values.txt')}")

    # -------------------- zeroize_dump / zeroize -------------------- #
    def start_zeroize_dump(self):
        self.separator()
        m = self.mem_path_edit.text().strip()
        r = self.res_path_edit.text().strip()

        if not m or not r:
            QMessageBox.critical(self, "Error", "Provide mem file and results folder")
            return
        if not os.path.isfile(m):
            QMessageBox.critical(self, "Error", f"Memory file not found:\n{m}")
            return

        # --- collect selected algorithms & corresponding value files --- #
        algo_map = {
            "aes": ("-a", self.cb_aes_zero),
            "rsa": ("-r", self.cb_rsa_zero),
            "serpent": ("-s", self.cb_serpent_zero),
            "twofish": ("-t", self.cb_twofish_zero),
        }

        cli_args = []
        selected = []
        for name, (flag, cb) in algo_map.items():
            if cb.isChecked():
                val_path = os.path.join(r, f"{name}_values.txt")
                if not os.path.isfile(val_path):
                    QMessageBox.critical(self, "Error", f"{val_path} not found. Run {name} finder first.")
                    return
                cli_args.extend([flag, val_path])
                selected.append(name)

        if not selected:
            QMessageBox.information(self, "Nothing selected", "Select at least one algorithm to zeroize.")
            return

        # --- locate zeroize_dump binary --- #
        dump_bin = os.path.join("Zeroizer", "zeroize_dump") if os.path.isfile(os.path.join("Zeroizer", "zeroize_dump")) else "./zeroize_dump"
        if not os.path.isfile(dump_bin):
            QMessageBox.critical(self, "Error", "zeroize_dump binary not found. Build Zeroizer first (run startup tasks).")
            return
        os.chmod(dump_bin, 0o755)

        # --- destination file --- #
        filename = self.zero_filename_edit.text().strip()
        if not filename:
            filename = "zero_mem.mem"
        if not filename.lower().endswith(".mem"):
            filename += ".mem"
        out_file = os.path.join(r, filename)

        # --- run --- #
        cmd = [dump_bin, *cli_args, "-o", out_file, m]
        self.log("Zeroizing selected keys, please wait…")
        self.log("Running: " + " ".join(cmd))

        self.dump_worker = CommandWorker(cmd)
        self.dump_worker.output.connect(self.log)
        self.dump_worker.finished.connect(lambda code: self.log(f"zeroize_dump finished with exit code {code}\nZeroed dump saved to: {out_file}" if code == 0 else "zeroize_dump failed"))
        self.dump_worker.start()


# ------------------------------ main ------------------------------------- #
if __name__ == "__main__":
    
    if not os.environ.get("XDG_RUNTIME_DIR"):
        os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{os.geteuid()}"

    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec_())
