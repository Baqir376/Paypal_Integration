# Recording scripts

Two pairs of sales calls to read aloud into a phone and upload — one in
English, one in Roman Urdu. They exist because checking whether an analysis is
*right* needs a call whose answer is known in advance, and no such recording
exists publicly for a Pakistani sales floor.

Each pair is a discovery call that stalls, and the follow-up that closes. Both
carry the same two objections, so the second call should score higher for a
reason you can point at rather than a reason the model asserted.

Read them naturally rather than performing them: pause, overlap slightly, say
"hmm", let the odd sentence trail off. A clean reading defeats the purpose —
the point is to give the diarizer and the metrics engine something real.

**A** is the salesperson. **B** is the customer, an operations head at a
mid-sized distribution company.

---

## How to record

1. Two phones, or one phone on speaker with both of you in a quiet room. Room
   noise is fine and actually useful — it is what a real call sounds like.
2. Do **not** read fast. Leave a beat before answering; that pause is what the
   patience metric measures, and it is the number synthetic audio cannot fake.
3. Interrupt each other once or twice. The engine counts interruptions and
   synthetic audio never contains one.
4. Save as `.mp3`, `.wav`, `.m4a` or `.ogg`. Under 200 MB.
5. Upload at `/upload`, pick the matching language, mark the outcome
   **Still open**.

## What to check afterwards

| Where | What should be true |
|---|---|
| Transcript | Latin letters throughout. For the Urdu calls: Roman Urdu, never Nastaliq and never Devanagari. |
| Speakers | Every line attributed to the right person. |
| Objections | Two found in call 1 — **price** and **status quo** — both unhandled. |
| Patience | Over 600 ms. Synthetic audio gives about 300. |
| Interruptions | Non-zero, if you actually interrupted. |
| Call 2 | Objections handled, a next step agreed, and a higher score than call 1. |

If call 1 scores higher than call 2, something is wrong and it is worth
reporting with both call ids.

---

# English

## CALL 1 — Discovery. Two objections, neither resolved.

**A:** Morning, Bilal. Thanks for making the time — I will not take more than
you have got.

**B:** No problem. I have got about twenty minutes.

**A:** Before I pitch anything, I just want to understand how renewals run for
you right now.

**B:** Honestly, most of it is manual. The team keeps dates in a spreadsheet
and we call the client about a month before expiry. It has worked fine so far.

**A:** Fair enough. How much of the week goes into the reporting side of that?

**B:** I have never actually counted. Six to eight hours, probably, because
the data sits in three separate systems and none of them talk to each other.
It is tedious but it is accurate.

**A:** So roughly thirty hours a month. If the team got that back, what would
they do with it?

**B:** Deeper pipeline analysis, maybe. The strategic work we push into next
quarter every quarter. But look — I have heard this before. "Save your team
time" is what every vendor opens with.

**A:** I understand. Have you tried a tool like this before?

**B:** We bought one two years ago. Six months later nobody was using it. The
implementation dragged on so long the team went back to the old way. I have
been careful with vendors since.

**A:** That is reasonable. What was the harder part — the setup, or getting the
team to use it afterwards?

**B:** The setup. Three weeks just to connect the data, and normal work carried
on the whole time. My team was already stretched.

**A:** Understood. Let us talk about price, since it is coming anyway.

**B:** Yes, and frankly the quote I have seen is well above what we budgeted.
We had not planned for a tool at that level.

**A:** If it saves thirty hours a month, that is a trade rather than a cost.
Which number does your leadership actually care about?

**B:** Revenue retention, and sales cycle speed. Saving hours does not move
either of those. If I take this budget upstairs I have to show an effect on
those two. Hours saved is not an argument for them.

**A:** Right. Let me propose a small pilot — reporting only, three weeks. If
the time is not there, we stop.

**B:** A pilot is still extra work for my team. Three weeks means putting
somebody on it. I would need to know what you expect from us during that,
otherwise this is the last time all over again.

**A:** That is fair. I will send you the detail this week.

**B:** Do that. I will look and come back to you.

## CALL 2 — The follow-up that closes. Record this only after call 1.

**A:** Morning, Bilal. Last time you raised two things — the implementation
burden, and that hours saved is not an argument for your leadership. I have
come back on both.

**B:** Go on.

**A:** First: setup needs one hour of your team's time. We do the data
connection at our end. The three weeks last time was because your team was
doing it.

**B:** One hour? Really?

**A:** One hour, and that is only to grant access. The second point matters
more. I looked at three customers your size. After they automated reporting,
their sales cycle shortened by eleven days on average — not because time was
saved, but because the renewal conversation started earlier.

**B:** Eleven days. That is interesting. What happened to retention?

**A:** Two of the three saw retention rise four to five percent. The third saw
no change at all, and I am telling you that so the picture is complete.

**B:** I appreciate you mentioning the third. Most people do not.

**A:** It does not help anyone. Now, price — you said it was above budget. What
if we tie the contract to that eleven-day number?

**B:** Meaning if the cycle does not shorten?

**A:** Then you do not pay the second year. In writing, in the contract.

**B:** That I can take upstairs. I will need to speak to my CFO, but now I have
something to bring.

**A:** Half an hour next Tuesday — you, your CFO and me. I will bring the
numbers from those three customers.

**B:** Tuesday works. I will send the invite.

**A:** Thanks, Bilal. Speak Tuesday.

---

# Roman Urdu

Upload with **Language: Roman Urdu**.

## CALL 1 — Discovery. Buyer holds two objections and neither is resolved.

**A:** Assalam-o-alaikum, Bilal sahab. Waqt dene ka shukriya. Main aap ka
zyada waqt nahi loonga.

**B:** Walaikum assalam. Haan boliye, mere paas taqreeban bees minute hain.

**A:** Kuch bechne se pehle main sirf yeh samajhna chahta hoon ke abhi aap ka
renewal process kaise chalta hai.

**B:** Dekhein, zyada tar kaam manual hi hai. Team ek spreadsheet mein dates
rakhti hai, aur hum expiry se ek mahina pehle client ko call kar lete hain.
Ab tak theek chal raha hai.

**A:** Theek hai. Aur reporting mein team ka hafte mein kitna waqt jata hai?

**B:** Maine kabhi count nahi kiya. Chhe se aath ghante lag hi jate hain,
kyunke data teen alag systems mein para hai aur wo aapas mein baat nahi karte.
Kaam thakane wala hai lekin accurate hai.

**A:** To mahine ke taqreeban tees ghante. Agar wo waqt team ko wapas mil
jaye, to wo us se kya karti?

**B:** Shayad pipeline ka thora gehra analysis. Jo strategic kaam hum har
quarter agle quarter par daal dete hain. Lekin dekhein, yeh baat main pehle
bhi sun chuka hoon. "Team ka waqt bachao" — har vendor yehi kehta hai.

**A:** Samajh sakta hoon. Aap ne pehle koi aisa tool try kiya tha?

**B:** Do saal pehle ek liya tha. Chhe mahine baad koi use hi nahi kar raha
tha. Implementation itni lambi thi ke team wapas apne purane tareeqe par chali
gayi. Us ke baad se main aise vendors se thora bach kar rehta hoon.

**A:** Wo jaiz hai. Us waqt sab se zyada mushkil kya thi — setup, ya baad mein
team ka use karna?

**B:** Setup. Teen hafte lag gaye the sirf data connect karne mein, aur us
dauran normal kaam bhi chalta raha. Meri team pehle hi thak chuki thi.

**A:** Achha. Ab price ki baat karte hain, kyunke wo waise bhi aayegi.

**B:** Haan, aur sach batayein to jo quote maine dekha hai wo hamare budget se
kaafi upar hai. Aisi tool ke liye hum ne itna soncha nahi tha.

**A:** Agar mahine ke tees ghante bach rahe hain, to yeh kharcha nahi, ek
trade hai. Aap ki leadership ke liye kaun sa number sab se zyada maayne rakhta
hai?

**B:** Revenue retention, aur sales cycle ki speed. Sirf ghante bachane se yeh
dono behtar nahi hote. Agar main yeh budget approve karwaun, to mujhe apni
leadership ko in dono par asar dikhana parega. Ghante bachana un ke liye
argument nahi hai.

**A:** Theek hai. Main ek chhota pilot tajweez karta hoon — sirf reporting
par, teen hafte. Agar waqt nahi bacha to hum aage nahi barhte.

**B:** Pilot bhi meri team ke liye extra kaam hai. Aur teen hafte ka matlab
hai koi banda us par lagana. Mujhe pehle yeh samajhna hoga ke us dauran aap
hum se kya expect kar rahe hain, warna yeh pichli dafa wali kahani ho jayegi.

**A:** Wajib baat hai. Main aap ko is hafte tafseel bhej deta hoon.

**B:** Theek hai, bhej dein. Main dekh kar batata hoon.

## CALL 2 — Follow-up jo close hoti hai. Sirf CALL 1 ke baad record karein.

**A:** Assalam-o-alaikum Bilal sahab. Pichli baar aap ne do cheezein kahi
theen — implementation ka bojh, aur yeh ke ghante bachana aap ki leadership
ke liye argument nahi hai. Main un dono par kaam kar ke aaya hoon.

**B:** Walaikum assalam. Achha, suniye.

**A:** Pehli baat: setup ke liye aap ki team ka waqt sirf ek ghanta chahiye.
Data connection hamari taraf se hogi. Pichli dafa jo teen hafte lage the, wo
is liye ke aap ki team khud kar rahi thi.

**B:** Ek ghanta? Sach mein?

**A:** Ek ghanta, aur wo bhi sirf access dene ke liye. Doosri baat zyada aham
hai. Main ne aap ke jaise teen customers ka data dekha. Reporting automate
karne ke baad un ka sales cycle ausatan gyarah din chhota hua — is liye nahi ke
waqt bacha, balke is liye ke renewal conversation pehle shuru ho gayi.

**B:** Gyarah din... yeh interesting hai. Retention par kya asar tha?

**A:** Do customers mein retention chaar se paanch percent barha. Teesre mein
koi farq nahi para, aur main wo bhi bata raha hoon taake baat poori rahe.

**B:** Achha lagta hai ke aap ne teesra bhi bataya. Zyada tar log nahi batate.

**A:** Us ka faida nahi hota. Ab price — aap ne kaha tha budget se upar hai.
Agar hum contract ko us gyarah din wale number se link kar dein, to?

**B:** Matlab agar cycle chhota na hua to?

**A:** To doosre saal ki fees aap nahi dete. Likha hua, contract mein.

**B:** Yeh mere liye argument ban sakta hai. Mujhe apni CFO se baat karni
paregi, lekin ab mere paas le jane ke liye kuch hai.

**A:** Agli hafte mangal ko aadha ghanta le lein — aap, CFO aur main. Main wo
teen customers ka number le kar aata hoon.

**B:** Mangal theek hai. Main invite bhej deta hoon.

**A:** Shukriya Bilal sahab. Mangal ko baat hoti hai.
