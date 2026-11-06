# Walking someone through the platform

Three families, three stories, one sitting of about ten minutes. Everything the
families see arrives by themselves as the network answers; you only play the hospital
staff.

## Before you start

1. Sign in to the control centre as an administrator.
2. **Configuration > Demo families**: type the address each family's sign-in code should
   go to (one per family, or fewer to load fewer) and press **Load the demo families**.
   Pressing it again puts every family back at the start of its story.
3. Each family signs in to the family app (web or Android) with *their* address. A code
   is emailed; see `docs/deploy.md` for setting up the email service.

| Family | Story | What it shows |
|---|---|---|
| 1. Anita Sharma | A smooth journey | The whole chain filling in by itself |
| 2. Ravi Kumar | A vendor fails | A problem, staff recovering, back on track |
| 3. Meena Gupta | Dialysis | A second condition on the same engine |

## The script

**Open the Network board** (control centre). The columns are every party a journey leans on,
including the hospital's own promises: a confirmed **Slot** and an available **Doctor** (and a
**Bed** when one is recorded). Family 1 is waiting on a report, family 2's
care steps are all done, family 3 has a dialysis session tomorrow.

### 1. Anita: the chain fills in by itself
1. Family 1 opens the app. *Journey*: "Now: Reports. We are working on this. You do not need
   to do anything." No date.
2. In **Releases**, mark Anita's pathology report released.
3. Within a minute and a half the scheme desk, the pharmacy, a cab and a room each answer,
   one after another. Anita's phone gets a short update in Hindi at each step, and the
   chain ticks along.
4. It ends on **GO**: the date, what to bring, and the first desk to go to.

### 2. Ravi: a vendor fails and staff recover
1. Family 2's ride was asked of Uber. About half a minute later Uber says it cannot.
2. Ravi's app shows **Problem** on the ride: "Our team is arranging another way. Please do
   not travel yet." No date is promised.
3. On the Network board the ride cell is red and Uber is counted as holding a journey.
4. Open Ravi in **Families**, the *Ride, stay, medicine, insurer* layer, and press
   **Book another**. Ola is asked and says yes after half a minute.
5. Ravi is back on **GO** and is told so.

### 3. Meena: a second condition
1. Family 3's chain is different: no pharmacy or scheme step, a ride, and a **Next session**
   at the end that is never given a date in advance.
2. A cab answers by itself and she is on **GO** for tomorrow's session.

## What to point out
- The families never see a date that is not promised, and never see a medical word.
- Every stage cites the record it rests on (the audit log shows the same chain).
- **Directory** holds every lab, pharmacy, distributor, cab and hotel the chain draws on.
  Edit an organisation to change how it answers: that is how family 2's Uber was made to fail.
- **Onboarding** is how a real family would be taken on: what they tell us first, then what
  the hospital adds for each admission.
