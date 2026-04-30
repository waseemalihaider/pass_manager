# GMB Lead Extractor Pro
## Poora Setup Guide (Roman Urdu)

---

## 📁 Files List
```
gmb_scraper/
├── app.py          ← Main program
├── START.bat       ← Yeh double click karo start karne ke liye
├── requirements.txt
└── templates/
    └── index.html  ← Admin panel design
```

---

## 🚀 Kaise Use Karein?

### Step 1 - Folder Copy Karo
- Yeh poora `gmb_scraper` folder apne PC mein kisi jagah rakh lo
- Example: `C:\gmb_scraper\` ya `E:\gmb_scraper\`

### Step 2 - Libraries Install Karo (Sirf Pehli Baar)
CMD mein jao aur yeh type karo:
```
pip install flask selenium webdriver-manager requests
```

### Step 3 - Start Karo
- `START.bat` file pe double click karo
- Ek black window khulegi (band mat karna!)
- Browser mein kholo: `http://localhost:5000`

---

## 🎯 Admin Panel Use Karna

1. **Country Select karo** - Europe ke 35+ countries available hain
2. **City Select karo** - Country ke baad city options aayenge
3. **Business Category Select karo** - 40+ categories available hain
4. **Windows Set karo** - + aur - se windows badhao/ghatao (1-5)
5. **Start Searching dabaao** - Kaam shuru!

---

## 📊 Results Mein Kya Milega?

- ✅ Business Name
- ✅ Email Address
- ✅ Phone Number  
- ✅ WhatsApp Check (Green = WA hai, Red = nahi)
- ✅ Website Link
- ✅ Address
- ✅ Rating

---

## 💾 Export Karna

Jab results aa jayein toh **CSV Export** button dabaao
- Excel mein khul jayega
- Saari details spreadsheet mein hongi

---

## ⚠️ Important Notes

1. **Google Maps** automatically Chrome mein khulega - kuch nahi karna
2. **Incognito windows** automatic khulti hain
3. Zyada windows = tez scraping lekin CPU zyada use hoga
4. Agar Chrome update maange toh update kar lo
5. Program chalte waqt black CMD window band mat karna

---

## 🔧 Problem Ho Toh?

**"Chrome not found" error:**
- Google Chrome install karo: google.com/chrome

**"Python not found" error:**
- Python install karo: python.org (Add to PATH checkbox zaroor tick karo)

**Page nahi khul raha:**
- Dekhlo START.bat chal raha hai ya nahi
- Browser mein: http://127.0.0.1:5000

---

## 📞 Support
Koi masla ho toh poochh lena!
