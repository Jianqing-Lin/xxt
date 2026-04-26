import uvicorn


if __name__ == "__main__":
    print("Autumn-xxt WebUI starting at http://127.0.0.1:8000/")
    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, reload=False)
