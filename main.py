from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.user import router as user_router
from routes.products import router as product_router
from routes.purchases import router as purchase_router
from routes.Sales import router as sales_router
from routes.customer import router as customer_router
from routes.debt import router as debt_router
from routes.report import router as report_router
from routes.expenditure import router as expenditure_router


app = FastAPI()

app.include_router(user_router, tags=["Users"])
app.include_router(product_router, tags=["Products"])
app.include_router(purchase_router, tags=["Purchases"])
app.include_router(sales_router, tags=["Sales"])
app.include_router(customer_router, tags=["Customers"])
app.include_router(debt_router, tags=["Debts"])
app.include_router(report_router, tags=["Reports"])
app.include_router(expenditure_router, tags=["Expenditures"])


#CORS configuration to allow from all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)




@app.get('/')
async def root():
    return {"message": "Hello, this is shopygeinie backend!"}


#running the server with reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
