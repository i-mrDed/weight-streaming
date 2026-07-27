"""Native file/directory picker helper (run as subprocess)."""
import sys
import os

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "file"
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as e:
        print(f"ERROR:tkinter not available: {e}", file=sys.stderr)
        sys.exit(2)

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()
    # Keep window alive briefly so dialog stays on top on Windows
    root.update_idletasks()
    root.update()

    path = ""
    if mode == "dir":
        path = filedialog.askdirectory(
            parent=root,
            title="Select Model Directory",
            mustexist=True,
        )
    else:
        path = filedialog.askopenfilename(
            parent=root,
            title="Select GGUF Model",
            filetypes=[
                ("GGUF Models", "*.gguf"),
                ("All Files", "*.*"),
            ],
        )

    root.destroy()
    if path:
        # Print absolute path only (stdout is the return channel)
        print(os.path.abspath(path), flush=True)
        sys.exit(0)
    sys.exit(1)  # cancelled


if __name__ == "__main__":
    main()
