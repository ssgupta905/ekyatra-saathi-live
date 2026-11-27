import { useState } from "react";
import { partner, type RateIn } from "@saathi/api-client";

/**
 * A vendor asking to join the network.
 *
 * The only screen in this app that works without an account, which is only
 * safe because of what it creates: an organisation that is switched off. No
 * family can be sent to it, no job can reach it, and it cannot see anything.
 * Somebody at the hospital decides, and that is said here rather than implied,
 * because a form that looks like a sign-up and behaves like an application
 * will be read as the former by everyone who fills it in.
 *
 * It asks for rates up front. A vendor's own price list is the single most
 * useful thing it can give this system: every figure Saathi shows a family is
 * marked as stated or estimated, and a vendor's stated rate is how a figure
 * gets to be the former.
 */

const TYPES: { id: string; label: string }[] = [
  { id: "cab", label: "Cab or auto service" },
  { id: "travel", label: "Travel operator — bus, van, train desk" },
  { id: "hotel", label: "Hotel, lodge or dharamshala" },
  { id: "pharmacy", label: "Pharmacy" },
  { id: "medicine_distributor", label: "Medicine distributor" },
  { id: "equipment_distributor", label: "Equipment distributor" },
  { id: "lab", label: "Diagnostic lab" },
  { id: "ambulance", label: "Ambulance" },
  { id: "insurer", label: "Insurer or scheme desk" },
  { id: "shop", label: "Shop" },
];

const BLANK_RATE: RateIn = { service: "", unit: "per trip", amount_inr: 0, note: "" };

const slug = (name: string) =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);

export function Apply() {
  const [name, setName] = useState("");
  const [type, setType] = useState("cab");
  const [contact, setContact] = useState("");
  const [districts, setDistricts] = useState("");
  const [services, setServices] = useState("");
  const [hours, setHours] = useState("");
  const [address, setAddress] = useState("");
  const [note, setNote] = useState("");
  const [rates, setRates] = useState<RateIn[]>([{ ...BLANK_RATE }]);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const id = slug(name);
  const list = (text: string) =>
    text
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);

  const usable = rates.filter((r) => r.service.trim() && Number(r.amount_inr) > 0);
  const ready = name.trim().length >= 2 && id.length >= 2 && contact.trim().length >= 4;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const answer = await partner.apply({
        id,
        name: name.trim(),
        type,
        contact: contact.trim(),
        districts: list(districts),
        services: list(services),
        address: address.trim(),
        hours: hours.trim(),
        rate_card: usable.map((r) => ({
          service: r.service.trim(),
          unit: r.unit?.trim() || "per trip",
          amount_inr: Number(r.amount_inr),
          note: r.note?.trim() || "",
        })),
        note: note.trim(),
      });
      setSent(answer.what_happens_next);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (sent) {
    return (
      <div className="pt-app">
        <header className="pt-top">
          <span className="pt-brand">Saathi</span>
          <span className="pt-org">Application sent</span>
        </header>
        <main className="pt-scroll">
          <p className="pt-need">Thank you — that is with the hospital.</p>
          <p className="pt-detail">{sent}</p>
          <p className="pt-detail">
            Your short name is <strong>{id}</strong>. Keep it: the hospital will
            create your sign-in against it.
          </p>
          <a className="pt-btn" href="#">
            Back to sign in
          </a>
        </main>
      </div>
    );
  }

  return (
    <div className="pt-app">
      <header className="pt-top">
        <span className="pt-brand">Saathi</span>
        <span className="pt-org">Apply to join</span>
      </header>

      <main className="pt-scroll">
        <p className="pt-detail">
          Families travelling for cancer treatment need rides, rooms and
          medicines, often at short notice and often a long way from home. Tell
          us what you do and what you charge. Somebody at the hospital reads
          every application — nothing reaches you until they do.
        </p>

        <div className="pt-fields">
          <label>
            Your business name
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Gaya Travels" />
          </label>
          {name.trim().length >= 2 && (
            <p className="pt-none">
              Short name: <strong>{id}</strong> — this is what your sign-in will be created against.
            </p>
          )}
          <label>
            What you are
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            A number somebody can reach you on
            <input value={contact} onChange={(e) => setContact(e.target.value)} placeholder="+91 90000 11122" />
          </label>
          <label>
            Districts you cover
            <input
              value={districts}
              onChange={(e) => setDistricts(e.target.value)}
              placeholder="Gaya, Nalanda"
            />
          </label>
          <label>
            What you offer, in your own words
            <input
              value={services}
              onChange={(e) => setServices(e.target.value)}
              placeholder="station pickup, overnight to Mumbai"
            />
          </label>
          <label>
            Hours
            <input value={hours} onChange={(e) => setHours(e.target.value)} placeholder="24 hours" />
          </label>
          <label>
            Address
            <input value={address} onChange={(e) => setAddress(e.target.value)} />
          </label>
        </div>

        <h2 className="pt-h2">What you charge</h2>
        <p className="pt-detail">
          Your prices, in your words. We never change them, never average them,
          and never show a family a figure as yours that you did not give us.
        </p>
        {rates.map((rate, index) => (
          <div className="pt-rate" key={index}>
            <label>
              Service
              <input
                value={rate.service}
                onChange={(e) =>
                  setRates(rates.map((r, i) => (i === index ? { ...r, service: e.target.value } : r)))
                }
                placeholder="Gaya to Mumbai, sleeper"
              />
            </label>
            <label>
              Charged by
              <input
                value={rate.unit ?? ""}
                onChange={(e) =>
                  setRates(rates.map((r, i) => (i === index ? { ...r, unit: e.target.value } : r)))
                }
                placeholder="per trip"
              />
            </label>
            <label>
              Rupees
              <input
                inputMode="numeric"
                value={rate.amount_inr || ""}
                onChange={(e) =>
                  setRates(
                    rates.map((r, i) =>
                      i === index ? { ...r, amount_inr: Number(e.target.value.replace(/\D/g, "")) } : r,
                    ),
                  )
                }
              />
            </label>
            <label>
              Anything that changes the price
              <input
                value={rate.note ?? ""}
                onChange={(e) =>
                  setRates(rates.map((r, i) => (i === index ? { ...r, note: e.target.value } : r)))
                }
                placeholder="₹200 more after 10pm"
              />
            </label>
          </div>
        ))}
        <button type="button" className="pt-btn" onClick={() => setRates([...rates, { ...BLANK_RATE }])}>
          Add another rate
        </button>

        <h2 className="pt-h2">Anything else</h2>
        <label className="pt-reason">
          Tell the hospital whatever matters
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Four cars, two drivers who have done hospital runs for years."
          />
        </label>

        {error && <p className="pt-error">{error}</p>}

        <div className="pt-actions" style={{ marginTop: 18 }}>
          <button type="button" className="pt-btn primary" disabled={busy || !ready} onClick={submit}>
            {busy ? "Sending…" : "Send the application"}
          </button>
          <a className="pt-btn" href="#">
            I already have an account
          </a>
        </div>
        <p className="pt-none" style={{ marginTop: 14 }}>
          You will never be asked here for anything about a patient, and this
          app never shows you one. You see the jobs you are asked to do, and
          nothing else.
        </p>
      </main>
    </div>
  );
}
