import os

def fault_active(name: str) -> bool:
    return name in os.getenv("inject_fault","").split(",")
