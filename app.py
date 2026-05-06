import runpy


if __name__ == "__main__":
    # Delegate to the real backend entrypoint while preserving its __main__ startup.
    runpy.run_module("PythonProject.app", run_name="__main__")
