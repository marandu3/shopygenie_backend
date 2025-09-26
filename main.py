from fastapi import FastAPI
from routes.user import router as user_router


app = FastAPI()

app.include_router(user_router, tags=["Users"])


@app.get('/')
async def root():
    return {"message": "Hello, this is shopygeinie backend!"}


#running the server with reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
