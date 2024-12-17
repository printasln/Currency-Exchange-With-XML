from fastapi import FastAPI, HTTPException
from sqlalchemy import Column, Integer, String, Float, Date, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import requests
import xml.etree.ElementTree as ET
from datetime import date

app = FastAPI()

DATABASE_URL = "sqlite:///./exchange_rates.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    id = Column(Integer, primary_key=True, index=True)
    currency_code = Column(String, index=True)
    rate = Column(Float, nullable=False)
    date = Column(Date, default=date.today)

Base.metadata.create_all(bind=engine)

EXTERNAL_XML_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"

def fetch_exchange_rates():
    try:
        response = requests.get(EXTERNAL_XML_URL)
        response.raise_for_status()
        xml_data = response.content
        tree = ET.ElementTree(ET.fromstring(xml_data))
        root = tree.getroot()

        rates = []
        for currency in root.findall('Currency'):
            code = currency.get('CurrencyCode')
            forex_buying = currency.find('ForexBuying').text
            if forex_buying:  # Ensure there is a valid rate
                rates.append({
                    "currency_code": code,
                    "rate": float(forex_buying),
                    "date": date.today()
                })
        return rates
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching XML data: {str(e)}")

def save_rates_to_db(rates):
    db = SessionLocal()
    try:
        for rate in rates:
            existing_rate = db.query(ExchangeRate).filter_by(currency_code=rate["currency_code"], date=rate["date"]).first()
            if not existing_rate:
                new_rate = ExchangeRate(
                    currency_code=rate["currency_code"],
                    rate=rate["rate"],
                    date=rate["date"]
                )
                db.add(new_rate)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error saving data to the database: {str(e)}")
    finally:
        db.close()

@app.get("/fetch-rates/")
def fetch_and_store_rates():
    rates = fetch_exchange_rates()
    save_rates_to_db(rates)
    return {"message": "Exchange rates fetched and stored successfully", "data": rates}

@app.get("/rates/")
def get_rates():
    db = SessionLocal()
    try:
        rates = db.query(ExchangeRate).all()
        return rates
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data from the database: {str(e)}")
    finally:
        db.close()

@app.get("/convert/")
def convert_currency(amount: float, from_currency: str, to_currency: str):
    db = SessionLocal()
    try:
        from_rate = db.query(ExchangeRate).filter_by(currency_code=from_currency).order_by(ExchangeRate.date.desc()).first()
        to_rate = db.query(ExchangeRate).filter_by(currency_code=to_currency).order_by(ExchangeRate.date.desc()).first()

        if not from_rate or not to_rate:
            raise HTTPException(status_code=404, detail="Currency code not found")

        converted_amount = amount * (to_rate.rate / from_rate.rate)
        return {
            "amount": amount,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "converted_amount": converted_amount
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error converting currency: {str(e)}")
    finally:
        db.close()
