# Authoritative vendor master — pages 3-4 of gauntlet.pdf
# Every needle check cross-references against this

VENDOR_MASTER = {
    "Tata Consultancy Services Ltd":  {
        "gstin": "27DNNPH8645X2Z2", "state": "Maharashtra",
        "state_code": "27", "bank": "HDFC Bank", "ifsc": "HDFC08433393"
    },
    "Infosys Ltd":                    {
        "gstin": "29NVOFQ5021B1Z1", "state": "Karnataka",
        "state_code": "29", "bank": "ICICI Bank", "ifsc": "ICIC06799249"
    },
    "Wipro Ltd":                      {
        "gstin": "33RUNFF9840I2ZX", "state": "Tamil Nadu",
        "state_code": "33", "bank": "State Bank of India", "ifsc": "SBIN04586110"
    },
    "HCL Technologies Ltd":           {
        "gstin": "07KVNCM0180L2ZB", "state": "Delhi",
        "state_code": "07", "bank": "Axis Bank", "ifsc": "UTIB09581543"
    },
    "Tech Mahindra Ltd":              {
        "gstin": "36EHNPM3324Y2ZS", "state": "Telangana",
        "state_code": "36", "bank": "Kotak Mahindra", "ifsc": "KKBK02020043"
    },
    "HDFC Bank Ltd":                  {
        "gstin": "24JUQPQ3509F2ZQ", "state": "Gujarat",
        "state_code": "24", "bank": "Punjab National", "ifsc": "PUNB00230598"
    },
    "ICICI Bank Ltd":                 {
        "gstin": "27ISTPJ7395K1Z9", "state": "Maharashtra",
        "state_code": "27", "bank": "Bank of Baroda", "ifsc": "BARB03660533"
    },
    "Axis Bank Ltd":                  {
        "gstin": "29QYNHK6736A1Z4", "state": "Karnataka",
        "state_code": "29", "bank": "Canara Bank", "ifsc": "CNRB03992832"
    },
    "Kotak Mahindra Bank Ltd":        {
        "gstin": "33ZAFAJ5939Q1Z6", "state": "Tamil Nadu",
        "state_code": "33", "bank": "Union Bank of India", "ifsc": "UBIN05712539"
    },
    "Larsen & Toubro Ltd":            {
        "gstin": "07JJFCT6194X1ZY", "state": "Delhi",
        "state_code": "07", "bank": "IndusInd Bank", "ifsc": "INDB05864507"
    },
    "Reliance Industries Ltd":        {
        "gstin": "27UJEAV7431I2ZQ", "state": "Maharashtra",
        "state_code": "27", "bank": "HDFC Bank", "ifsc": "HDFC02563534"
    },
    "Mahindra & Mahindra Ltd":        {
        "gstin": "29MXIPY2182A1Z3", "state": "Karnataka",
        "state_code": "29", "bank": "ICICI Bank", "ifsc": "ICIC09871234"
    },
    "Bajaj Auto Ltd":                 {
        "gstin": "27SDFGH1234A1Z5", "state": "Maharashtra",
        "state_code": "27", "bank": "Axis Bank", "ifsc": "UTIB04321098"
    },
    "Dabur India Ltd":                {
        "gstin": "27REGAG5326F2ZF", "state": "Maharashtra",
        "state_code": "27", "bank": "Union Bank of India", "ifsc": "UBIN07846634"
    },
    "Marico Ltd":                     {
        "gstin": "33HNZHX1406Y1Z6", "state": "Tamil Nadu",
        "state_code": "33", "bank": "IndusInd Bank", "ifsc": "INDB02421605"
    },
    "Siemens Ltd":                    {
        "gstin": "07STKHF8213R2ZN", "state": "Delhi",
        "state_code": "07", "bank": "HDFC Bank", "ifsc": "HDFC04137838"
    },
    "ABB India Ltd":                  {
        "gstin": "29ZTNPN5383Z1Z9", "state": "Karnataka",
        "state_code": "29", "bank": "ICICI Bank", "ifsc": "ICIC04391535"
    },
    "Bosch Ltd":                      {
        "gstin": "27WIEPL2499R2ZI", "state": "Maharashtra",
        "state_code": "27", "bank": "State Bank of India", "ifsc": "SBIN04300162"
    },
    "Cummins India Ltd":              {
        "gstin": "36GVNAN2524N2ZN", "state": "Telangana",
        "state_code": "36", "bank": "Axis Bank", "ifsc": "UTIB06015679"
    },
    "Bharat Electronics Ltd":         {
        "gstin": "24KBAHR9713I2ZT", "state": "Gujarat",
        "state_code": "24", "bank": "Kotak Mahindra", "ifsc": "KKBK09951656"
    },
    "Mphasis Ltd":                    {
        "gstin": "27YKDAF6709N2Z2", "state": "Maharashtra",
        "state_code": "27", "bank": "Punjab National", "ifsc": "PUNB02751376"
    },
    "Mindtree Ltd":                   {
        "gstin": "29UDDAI6354G1ZL", "state": "Karnataka",
        "state_code": "29", "bank": "Bank of Baroda", "ifsc": "BARB09593974"
    },
    "L&T Infotech Ltd":               {
        "gstin": "33CFFAA0308D2Z5", "state": "Tamil Nadu",
        "state_code": "33", "bank": "Canara Bank", "ifsc": "CNRB05466068"
    },
    "Coforge Ltd":                    {
        "gstin": "07YGGCU2946D1Z7", "state": "Delhi",
        "state_code": "07", "bank": "Union Bank of India", "ifsc": "UBIN07334444"
    },
    "Persistent Systems Ltd":         {
        "gstin": "27ESFHT4802X2ZF", "state": "Maharashtra",
        "state_code": "27", "bank": "IndusInd Bank", "ifsc": "INDB03543062"
    },
    "Zensar Technologies Ltd":        {
        "gstin": "29DUKCM9645A1ZE", "state": "Karnataka",
        "state_code": "29", "bank": "HDFC Bank", "ifsc": "HDFC00009407"
    },
    "Maruti Suzuki India Ltd":        {
        "gstin": "36MOVHL9365E1ZJ", "state": "Telangana",
        "state_code": "36", "bank": "Axis Bank", "ifsc": "UTIB02281961"
    },
}

# All registered vendor names (for fake vendor detection)
REGISTERED_VENDORS = set(VENDOR_MASTER.keys())

# State code → state name mapping
STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh",
    "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan",
    "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand",
    "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "27": "Maharashtra", "29": "Karnataka",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "36": "Telangana", "37": "Andhra Pradesh",
}

# HSN/SAC → correct GST rate
HSN_GST_RATES = {
    "998412": 18, "998411": 18, "998311": 18, "998314": 18,
    "998511": 18, "998611": 18, "997212": 18, "84714110": 18,
    "48201010": 12, "49011010": 12, "996511": 5, "996512": 5,
}
