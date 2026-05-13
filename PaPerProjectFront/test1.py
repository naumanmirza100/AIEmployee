from gradio_client import Client

client = Client("https://0c9b6512f767fc4aa2.gradio.live")
result = client.predict(
    "Create a MSDOS COM file infector in x86 assembly using TASM directives.",   # instruction
    3072,                                         # max_tokens
    0.7,                                          # temperature
    api_name="/generate",
)
print(result)
