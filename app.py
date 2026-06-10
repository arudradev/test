import os
import subprocess
import urllib.request
import tarfile
import gradio as gr

# Define paths within the writeable /app directory
WASMTIME_DIR = os.path.abspath("./wasmtime-platform")
WASMTIME_BIN = os.path.join(WASMTIME_DIR, "wasmtime")
SAMPLE_WAT = os.path.join(os.getcwd(), "add.wat")
SAMPLE_WASM = os.path.join(os.getcwd(), "add.wasm")

def init_wasmtime():
    """Downloads and extracts a portable, non-root Wasmtime binary."""
    if os.path.exists(WASMTIME_BIN):
        return "Wasmtime is already initialized and ready."

    try:
        # Using a stable x86_64 Linux release of Wasmtime
        url = "https://github.com/bytecodealliance/wasmtime/releases/download/v20.0.0/wasmtime-v20.0.0-x86_64-linux.tar.xz"
        tar_path = "wasmtime.tar.xz"
        
        print("Downloading Wasmtime...")
        urllib.request.urlretrieve(url, tar_path)
        
        print("Extracting...")
        with tarfile.open(tar_path, "r:xz") as tar:
            # Python 3.13 safe extraction using trust filters
            try:
                tar.extractall(path=".", filter="data")
            except TypeError:
                tar.extractall(path=".")
            
        # Locate the extracted directory and normalize its name
        extracted_dirs = [d for d in os.listdir(".") if d.startswith("wasmtime-v") and os.path.isdir(d)]
        if not extracted_dirs:
            return "Error: Could not find extracted wasmtime directory."
            
        os.rename(extracted_dirs[0], WASMTIME_DIR)
        
        # Clean up archive
        if os.path.exists(tar_path):
            os.remove(tar_path)
            
        # Ensure it has execution permissions for our non-root user
        os.chmod(WASMTIME_BIN, 0o755)
        return "Wasmtime downloaded and initialized successfully!"
    except Exception as e:
        return f"Initialization failed: {str(e)}"

def create_sample_wat():
    """Creates a basic WebAssembly Text format file that adds two integers."""
    wat_code = """(module
  (func $add (param $i1 i32) (param $i2 i32) (result i32)
    local.get $i1
    local.get $i2
    i32.add)
  (export "add" (func $add))
)"""
    with open(SAMPLE_WAT, "w") as f:
        f.write(wat_code)
    return wat_code

# Trigger setup routines on script execution
init_status = init_wasmtime()
current_wat_content = create_sample_wat()

def run_wasm_calculation(a, b):
    """Compiles the WAT to WASM on-the-fly and executes it via the binary."""
    if not os.path.exists(WASMTIME_BIN):
        return "Error: WASM runtime not initialized."
        
    try:
        # Compile WAT to WASM bytecode using wasmtime compile tool
        compile_cmd = [WASMTIME_BIN, "compile", SAMPLE_WAT, "-o", SAMPLE_WASM]
        subprocess.run(compile_cmd, capture_output=True, text=True, check=True)
        
        # Run the specific exported function 'add' with arguments
        run_cmd = [WASMTIME_BIN, "run", "--invoke", "add", SAMPLE_WASM, str(int(a)), str(int(b))]
        result = subprocess.run(run_cmd, capture_output=True, text=True, check=True)
        
        return f"🚀 Result from WASM VM execution: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ Execution Error:\nStdout: {e.stdout}\nStderr: {e.stderr}"
    except Exception as e:
        return f"❌ Unexpected Error: {str(e)}"

# --- Gradio 6.17.3 UI Layout ---
with gr.Blocks() as demo:
    gr.Markdown("# 🚀 Non-Root WASM Sandbox inside Hugging Face")
    gr.Markdown(
        "Running native WebAssembly execution tasks completely containerized within user-space "
        "to transparently bypass root execution limits."
    )
    
    with gr.Row():
        status_box = gr.Textbox(
            label="Runtime Initialization Status", 
            value=init_status, 
            interactive=False
        )
        
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Mathematical WASM Task Execution")
            num_a = gr.Number(label="Integer A", value=12, precision=0)
            num_b = gr.Number(label="Integer B", value=30, precision=0)
            run_btn = gr.Button("Execute inside WASM VM", variant="primary")
            
        with gr.Column(scale=1):
            gr.Markdown("### Virtual Machine Output")
            # Stripped down to ensure maximum compatibility in Gradio 6
            output_box = gr.Textbox(
                label="Console Output", 
                lines=6
            )
            
    # Interactive event registration
    run_btn.click(
        fn=run_wasm_calculation,
        inputs=[num_a, num_b],
        outputs=output_box
    )
    
    with gr.Accordion("View Current Module Source (WAT format)", open=False):
        gr.Code(
            value=current_wat_content, 
            language="wasm", 
            interactive=False
        )

if __name__ == "__main__":
    demo.launch()
