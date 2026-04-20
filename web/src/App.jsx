import { useEffect, useMemo, useState } from "react";
import { api, API_BASE } from "./api.js";
import { useInterval } from "./hooks.js";

const emptyAuth = { email: "", password: "", name: "", role: "buyer" };

function StepDots({ current = 1 }) {
  return (
    <div className="flex items-center gap-3">
      {[1, 2, 3, 4].map((step) => (
        <div key={step} className="flex items-center gap-3">
          <div
            className={`h-9 w-9 rounded-full flex items-center justify-center text-sm font-semibold ${
              step <= current ? "bg-ink text-white" : "bg-white/70 text-slate border border-slate/20"
            }`}
          >
            {step}
          </div>
          {step < 4 && <div className="h-px w-10 bg-slate/30" />}
        </div>
      ))}
    </div>
  );
}

function Chip({ children, tone = "default" }) {
  const tones = {
    default: "border-slate/30 text-slate",
    good: "border-mint/60 text-emerald-700",
    warn: "border-ember/60 text-amber-700",
    bad: "border-ember/70 text-red-700",
  };
  return (
    <span className={`badge border ${tones[tone] || tones.default}`}>{children}</span>
  );
}

function getResetTokenFromUrl() {
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get("token") || "";
  } catch {
    return "";
  }
}

export default function App() {
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState(emptyAuth);
  const [adminInvite, setAdminInvite] = useState("");
  const [token, setToken] = useState("");
  const [user, setUser] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [publicInventory, setPublicInventory] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [ledger, setLedger] = useState(null);
  const [disputes, setDisputes] = useState([]);
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminTransactions, setAdminTransactions] = useState([]);
  const [adminConfig, setAdminConfig] = useState({
    siteTitle: "TrustBridge",
    allowGuestView: true,
    requireAdminInvite: true,
  });

  const [inventoryForm, setInventoryForm] = useState({
    name: "",
    sku: "",
    price: "",
    stock: "",
    market_low: "",
    market_high: "",
    image_url: "",
  });

  const [selectedItemId, setSelectedItemId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [activeTxId, setActiveTxId] = useState("");
  const [autoPoll, setAutoPoll] = useState(true);
  const [inventoryImageFile, setInventoryImageFile] = useState(null);
  const [inventoryDriveLink, setInventoryDriveLink] = useState("");

  const [resetMode, setResetMode] = useState("request");
  const [resetEmail, setResetEmail] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [resetPassword, setResetPassword] = useState("");

  const selectedItem = useMemo(
    () => publicInventory.find((item) => item.id === selectedItemId),
    [publicInventory, selectedItemId]
  );

  useEffect(() => {
    loadPublicInventory();
    const savedToken = sessionStorage.getItem("tb_token");
    const savedUser = sessionStorage.getItem("tb_user");
    if (savedToken && savedUser) {
      const parsed = JSON.parse(savedUser);
      setToken(savedToken);
      setUser(parsed);
      loadPrivateData(savedToken);
    }
    const urlToken = getResetTokenFromUrl();
    if (urlToken) {
      setAuthMode("reset");
      setResetMode("confirm");
      setResetToken(urlToken);
    }
  }, []);

  useInterval(
    () => {
      if (autoPoll && activeTxId && token) {
        pollStatus(activeTxId);
      }
    },
    autoPoll ? 8000 : null
  );

  async function loadPublicInventory() {
    try {
      const data = await api("/inventory/public");
      setPublicInventory(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadAdminData(currentToken) {
    try {
      const users = await api("/admin/users", { token: currentToken });
      setAdminUsers(users);
    } catch {
      setAdminUsers([]);
    }
    try {
      const tx = await api("/admin/transactions", { token: currentToken });
      setAdminTransactions(tx);
    } catch {
      setAdminTransactions([]);
    }
  }

  async function loadPrivateData(currentToken = token) {
    if (!currentToken) return;
    try {
      const inv = await api("/inventory", { token: currentToken });
      setInventory(inv);
    } catch {
      setInventory([]);
    }
    try {
      const tx = await api("/transactions", { token: currentToken });
      setTransactions(tx);
    } catch {
      setTransactions([]);
    }
    try {
      const me = await api("/me", { token: currentToken });
      if (me.role === "admin") {
        const data = await api("/admin/disputes", { token: currentToken });
        setDisputes(data);
        await loadAdminData(currentToken);
      } else {
        setDisputes([]);
      }
    } catch {
      setDisputes([]);
    }
  }

  async function handleAuth(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      const path = authMode === "login" ? "/auth/login" : "/auth/register";
      const payload =
        authMode === "login"
          ? { email: authForm.email, password: authForm.password }
          : {
              email: authForm.email,
              password: authForm.password,
              role: authForm.role,
              name: authForm.name,
            };
      const headers =
        authMode === "register" && authForm.role === "admin"
          ? { "X-Admin-Invite": adminInvite }
          : undefined;
      const data = await api(path, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      setToken(data.token);
      setUser(data.user);
      sessionStorage.setItem("tb_token", data.token);
      sessionStorage.setItem("tb_user", JSON.stringify(data.user));
      setMessage(`Welcome ${data.user.name}`);
      await loadPrivateData(data.token);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleResetRequest(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await api("/auth/reset-request", {
        method: "POST",
        body: JSON.stringify({ email: resetEmail }),
      });
      setMessage("Reset email sent if the address exists.");
      setResetMode("request");
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleResetConfirm(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await api("/auth/reset-confirm", {
        method: "POST",
        body: JSON.stringify({ token: resetToken, new_password: resetPassword }),
      });
      setMessage("Password reset. You can log in now.");
      setResetMode("request");
      setResetEmail("");
      setResetToken("");
      setResetPassword("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCreateInventory(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      if (inventoryImageFile || inventoryDriveLink) {
        const formData = new FormData();
        formData.append("name", inventoryForm.name);
        formData.append("sku", inventoryForm.sku);
        formData.append("price", inventoryForm.price);
        formData.append("stock", inventoryForm.stock);
        if (inventoryForm.market_low) formData.append("market_low", inventoryForm.market_low);
        if (inventoryForm.market_high) formData.append("market_high", inventoryForm.market_high);
        if (inventoryImageFile) {
          formData.append("image_file", inventoryImageFile);
        }
        if (inventoryDriveLink) {
          formData.append("google_drive_link", inventoryDriveLink);
        }
        await fetch(`${API_BASE}/inventory/upload`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        }).then(async (res) => {
          if (!res.ok) {
            const json = await res.json().catch(() => null);
            throw new Error(json?.detail || "Inventory upload failed");
          }
          return res.json();
        });
      } else {
        await api("/inventory", {
          method: "POST",
          token,
          body: JSON.stringify({
            ...inventoryForm,
            price: Number(inventoryForm.price),
            stock: Number(inventoryForm.stock),
            market_low: inventoryForm.market_low ? Number(inventoryForm.market_low) : null,
            market_high: inventoryForm.market_high ? Number(inventoryForm.market_high) : null,
            image_url: inventoryForm.image_url || null,
          }),
        });
      }
      setMessage("Inventory added.");
      setInventoryForm({
        name: "",
        sku: "",
        price: "",
        stock: "",
        market_low: "",
        market_high: "",
        image_url: "",
      });
      setInventoryImageFile(null);
      setInventoryDriveLink("");
      await loadPrivateData();
      await loadPublicInventory();
    } catch (err) {
      setError(err.message);
    }
  }

  async function openRazorpayCheckout(transactionId, order) {
    if (!window.Razorpay) {
      setError("Razorpay SDK not loaded.");
      return;
    }
    const options = {
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      name: "TrustBridge",
      description: `Transaction ${transactionId}`,
      order_id: order.order_id,
      handler: async (response) => {
        try {
          const result = await api(`/transactions/${transactionId}/verify-payment`, {
            method: "POST",
            token,
            body: JSON.stringify({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            }),
          });
          setMessage(`Payment ${result.payment_status}.`);
          await loadPrivateData();
          await handleLedgerLookup(transactionId);
        } catch (err) {
          setError(err.message);
        }
      },
      prefill: {
        name: user?.name || "",
        email: user?.email || "",
      },
      theme: { color: "#0c0f12" },
    };
    const rz = new window.Razorpay(options);
    rz.open();
  }

  async function handleStartPayment() {
    if (!selectedItemId || !quantity) {
      setError("Select an item and quantity.");
      return;
    }
    setError("");
    setMessage("");
    try {
      const tx = await api("/transactions", {
        method: "POST",
        token,
        body: JSON.stringify({
          inventory_id: selectedItemId,
          quantity: Number(quantity),
        }),
      });
      const order = await api(`/transactions/${tx.id}/create-order`, {
        method: "POST",
        token,
      });
      await loadPrivateData();
      openRazorpayCheckout(tx.id, order);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleLedgerLookup(id) {
    setError("");
    setMessage("");
    try {
      const data = await api(`/ledger/${id}`, { token });
      setLedger(data);
      setActiveTxId(id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function downloadLedgerPdf(id) {
    setError("");
    setMessage("");
    try {
      const res = await fetch(`${API_BASE}/ledger/${id}/invoice`, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.detail || "Failed to download PDF");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ledger_${id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setMessage("Invoice downloaded.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function pollStatus(id) {
    try {
      const data = await api(`/transactions/${id}/poll-status`, { method: "POST", token });
      setMessage(`Status synced: ${data.payment_status}`);
      await loadPrivateData();
      await handleLedgerLookup(id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCreateDispute(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      const data = await api("/disputes", {
        method: "POST",
        token,
        body: JSON.stringify({
          transaction_id: activeTxId,
          reason: e.target.elements.reason.value,
        }),
      });
      setMessage(`Dispute opened: ${data.id}`);
      e.target.reset();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleResolveDispute(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    const disputeId = e.target.elements.dispute_id.value;
    const status = e.target.elements.status.value;
    const resolutionNote = e.target.elements.resolution_note.value;
    try {
      await api(`/admin/disputes/${disputeId}/resolve`, {
        method: "POST",
        token,
        body: JSON.stringify({ status, resolution_note: resolutionNote }),
      });
      setMessage("Dispute resolved.");
      e.target.reset();
      await loadPrivateData();
    } catch (err) {
      setError(err.message);
    }
  }

  function handleLogout() {
    setToken("");
    setUser(null);
    setInventory([]);
    setTransactions([]);
    setLedger(null);
    setDisputes([]);
    setMessage("Logged out.");
    sessionStorage.removeItem("tb_token");
    sessionStorage.removeItem("tb_user");
  }

  const progressStep = user
    ? user.role === "seller"
      ? 2
      : user.role === "buyer"
        ? 3
        : 4
    : 1;

  return (
    <div className="min-h-screen px-6 py-10">
      <div className="mx-auto max-w-6xl">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-sm uppercase tracking-[0.4em]">TrustBridge</div>
            <h1 className="section-title text-4xl mt-2">Trust Agent Flow</h1>
          </div>
          <div className="flex items-center gap-3">
            <StepDots current={progressStep} />
            {user ? (
              <button className="rounded-full border border-ink px-5 py-2" onClick={handleLogout}>
                Logout
              </button>
            ) : (
              <span className="badge">Unauthenticated</span>
            )}
          </div>
        </header>

        {(message || error) && (
          <div className="mt-6 grid gap-2">
            {message && <div className="glass rounded-2xl p-4">{message}</div>}
            {error && <div className="rounded-2xl border border-ember p-4 text-ember">{error}</div>}
          </div>
        )}

        {!user && (
          <section className="mt-10 grid gap-6 lg:grid-cols-[0.7fr_1.3fr]">
            <div className="glass rounded-3xl p-6">
              <h2 className="section-title text-2xl">Access</h2>
              <p className="text-slate mt-2">Choose a role to enter the flow.</p>
              <div className="mt-4 flex gap-2">
                <button
                  className={`rounded-full px-4 py-2 ${authMode === "login" ? "bg-ink text-white" : "border border-ink"}`}
                  onClick={() => setAuthMode("login")}
                >
                  Login
                </button>
                <button
                  className={`rounded-full px-4 py-2 ${authMode === "register" ? "bg-ink text-white" : "border border-ink"}`}
                  onClick={() => setAuthMode("register")}
                >
                  Register
                </button>
                <button
                  className={`rounded-full px-4 py-2 ${authMode === "reset" ? "bg-ink text-white" : "border border-ink"}`}
                  onClick={() => setAuthMode("reset")}
                >
                  Reset
                </button>
              </div>
            </div>

            {authMode !== "reset" ? (
              <form className="glass rounded-3xl p-6 grid gap-4" onSubmit={handleAuth}>
                {authMode === "register" && (
                  <>
                    <input
                      className="rounded-2xl border border-slate/30 p-3"
                      placeholder="Full name"
                      value={authForm.name}
                      onChange={(e) => setAuthForm({ ...authForm, name: e.target.value })}
                      required
                    />
                    <div className="grid grid-cols-3 gap-2">
                      {["buyer", "seller", "admin"].map((role) => (
                        <button
                          key={role}
                          type="button"
                          className={`rounded-2xl p-3 text-sm ${
                            authForm.role === role ? "bg-ink text-white" : "border border-slate/30"
                          }`}
                          onClick={() => setAuthForm({ ...authForm, role })}
                        >
                          {role}
                        </button>
                      ))}
                    </div>
                    {authForm.role === "admin" && (
                      <input
                        className="rounded-2xl border border-slate/30 p-3"
                        placeholder="Admin invite code"
                        value={adminInvite}
                        onChange={(e) => setAdminInvite(e.target.value)}
                        required
                      />
                    )}
                  </>
                )}
                <input
                  className="rounded-2xl border border-slate/30 p-3"
                  placeholder="Email"
                  type="email"
                  value={authForm.email}
                  onChange={(e) => setAuthForm({ ...authForm, email: e.target.value })}
                  required
                />
                <input
                  className="rounded-2xl border border-slate/30 p-3"
                  placeholder="Password"
                  type="password"
                  value={authForm.password}
                  onChange={(e) => setAuthForm({ ...authForm, password: e.target.value })}
                  required
                />
                <button className="rounded-full bg-ink text-white px-5 py-2">
                  {authMode === "login" ? "Login" : "Create Account"}
                </button>
              </form>
            ) : (
              <div className="glass rounded-3xl p-6 grid gap-4">
                <div className="flex gap-2">
                  <button
                    className={`rounded-full px-4 py-2 ${resetMode === "request" ? "bg-ink text-white" : "border border-ink"}`}
                    onClick={() => setResetMode("request")}
                  >
                    Request
                  </button>
                  <button
                    className={`rounded-full px-4 py-2 ${resetMode === "confirm" ? "bg-ink text-white" : "border border-ink"}`}
                    onClick={() => setResetMode("confirm")}
                  >
                    Confirm
                  </button>
                </div>
                {resetMode === "request" ? (
                  <form className="grid gap-3" onSubmit={handleResetRequest}>
                    <input
                      className="rounded-2xl border border-slate/30 p-3"
                      placeholder="Email"
                      type="email"
                      value={resetEmail}
                      onChange={(e) => setResetEmail(e.target.value)}
                      required
                    />
                    <button className="rounded-full bg-ink text-white px-5 py-2">Send reset</button>
                  </form>
                ) : (
                  <form className="grid gap-3" onSubmit={handleResetConfirm}>
                    <input
                      className="rounded-2xl border border-slate/30 p-3"
                      placeholder="Reset token"
                      value={resetToken}
                      onChange={(e) => setResetToken(e.target.value)}
                      required
                    />
                    <input
                      className="rounded-2xl border border-slate/30 p-3"
                      placeholder="New password"
                      type="password"
                      value={resetPassword}
                      onChange={(e) => setResetPassword(e.target.value)}
                      required
                    />
                    <button className="rounded-full bg-ink text-white px-5 py-2">Reset password</button>
                  </form>
                )}
              </div>
            )}
          </section>
        )}

        <section className="mt-12 grid gap-6">
          <div className="flex items-center justify-between">
            <h2 className="section-title text-2xl">Market Cards</h2>
            <button className="rounded-full border border-ink px-4 py-2" onClick={loadPublicInventory}>
              Refresh
            </button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {publicInventory.map((item) => (
              <button
                key={item.id}
                className={`text-left glass rounded-3xl p-5 border transition ${
                  selectedItemId === item.id ? "border-ink shadow-glow" : "border-transparent"
                }`}
                onClick={() => setSelectedItemId(item.id)}
              >
                <div className="flex gap-3 items-start">
                  <div className="w-20 h-20 rounded-2xl overflow-hidden bg-slate/10 flex items-center justify-center">
                    {item.image_url ? (
                      <img src={item.image_url} alt={item.name} className="h-full w-full object-cover" />
                    ) : (
                      <span className="text-xs text-slate">No image</span>
                    )}
                  </div>
                  <div className="flex-1 text-left">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate">{item.seller_name}</div>
                    <div className="text-xl font-semibold mt-2">{item.name}</div>
                    <div className="text-sm text-slate">SKU: {item.sku}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Chip tone="good">₹{item.price}</Chip>
                      <Chip>Stock {item.stock}</Chip>
                      {item.market_low && item.market_high && (
                        <Chip>₹{item.market_low} - ₹{item.market_high}</Chip>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </section>

        {user && user.role === "buyer" && (
          <section className="mt-12 grid gap-6">
            <div className="glass rounded-3xl p-6">
              <h2 className="section-title text-2xl">Buyer Console</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto] items-center">
                <div>
                  <div className="text-sm text-slate">Selected item</div>
                  <div className="text-lg font-semibold">
                    {selectedItem ? selectedItem.name : "Pick a market card"}
                  </div>
                  {selectedItem && (
                    <div className="text-sm text-slate">
                      ₹{selectedItem.price} | Stock {selectedItem.stock}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <input
                    className="rounded-2xl border border-slate/30 p-3 w-24"
                    type="number"
                    min="1"
                    value={quantity}
                    onChange={(e) => setQuantity(Number(e.target.value))}
                  />
                  <button className="rounded-full bg-ink text-white px-5 py-3" onClick={handleStartPayment}>
                    Start Verified Payment
                  </button>
                </div>
              </div>
            </div>
          </section>
        )}

        {user && user.role === "seller" && (
          <section className="mt-12 grid gap-8">
            <div className="glass rounded-3xl p-6">
              <h2 className="section-title text-2xl">Seller Inventory</h2>
              <form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={handleCreateInventory}>
                <input
                  className="rounded-2xl border border-slate/30 p-3"
                  placeholder="Item name"
                  value={inventoryForm.name}
                  onChange={(e) => setInventoryForm({ ...inventoryForm, name: e.target.value })}
                  required
                />
                <input
                  className="rounded-2xl border border-slate/30 p-3"
                  placeholder="SKU"
                  value={inventoryForm.sku}
                  onChange={(e) => setInventoryForm({ ...inventoryForm, sku: e.target.value })}
                  required
                />
                <input
                  className="rounded-2xl border border-slate/30 p-3"
                  placeholder="Price"
                  type="number"
                  value={inventoryForm.price}
                  onChange={(e) => setInventoryForm({ ...inventoryForm, price: e.target.value })}
                  required
                />
                <input
                  className="rounded-2xl border border-slate/30 p-3"
                  placeholder="Stock"
                  type="number"
                  value={inventoryForm.stock}
                  onChange={(e) => setInventoryForm({ ...inventoryForm, stock: e.target.value })}
                  required
                />
                <input
                  className="rounded-2xl border border-slate/30 p-3"
                  placeholder="Market low"
                  type="number"
                  value={inventoryForm.market_low}
                  onChange={(e) => setInventoryForm({ ...inventoryForm, market_low: e.target.value })}
                />
                <input
                  className="rounded-2xl border border-slate/30 p-3"
                  placeholder="Market high"
                  type="number"
                  value={inventoryForm.market_high}
                  onChange={(e) => setInventoryForm({ ...inventoryForm, market_high: e.target.value })}
                />
                <div className="md:col-span-2 grid gap-2">
                  <label className="text-sm font-medium">Upload product image (file)</label>
                  <input
                    className="rounded-2xl border border-slate/30 p-2"
                    type="file"
                    accept="image/*"
                    onChange={(e) => setInventoryImageFile(e.target.files[0] || null)}
                  />
                  <label className="text-sm font-medium">Or add Google Drive link</label>
                  <input
                    className="rounded-2xl border border-slate/30 p-3"
                    placeholder="Google Drive share link"
                    value={inventoryDriveLink}
                    onChange={(e) => setInventoryDriveLink(e.target.value)}
                  />
                  <div className="text-xs text-slate">If you upload a file, it will be stored and shown locally. Use one option only.</div>
                </div>
                <button className="rounded-full bg-ink text-white px-5 py-2 md:col-span-2">
                  Add Inventory
                </button>
              </form>
            </div>

            <div>
              <h2 className="section-title text-2xl">Your Inventory Cards</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {inventory.map((item) => (
                  <div key={item.id} className="glass rounded-3xl p-5">
                    <div className="text-xl font-semibold">{item.name}</div>
                    <div className="text-sm text-slate">SKU: {item.sku}</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Chip tone="good">₹{item.price}</Chip>
                      <Chip>Stock {item.stock}</Chip>
                      <Chip>Reserved {item.reserved}</Chip>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {user && (
          <section className="mt-12 grid gap-6">
            <div className="flex items-center justify-between">
              <h2 className="section-title text-2xl">Live Transactions</h2>
              <label className="flex items-center gap-2 text-sm text-slate">
                <input
                  type="checkbox"
                  checked={autoPoll}
                  onChange={(e) => setAutoPoll(e.target.checked)}
                />
                Auto-sync
              </label>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {transactions.map((tx) => (
                <button
                  key={tx.id}
                  className={`text-left glass rounded-3xl p-5 border transition ${
                    activeTxId === tx.id ? "border-ink shadow-glow" : "border-transparent"
                  }`}
                  onClick={() => handleLedgerLookup(tx.id)}
                >
                  <div className="text-xs uppercase tracking-[0.2em] text-slate">{tx.id}</div>
                  <div className="text-lg font-semibold mt-2">{tx.item_name}</div>
                  <div className="text-sm text-slate">Qty {tx.quantity} | ₹{tx.unit_price}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Chip tone={tx.payment_status === "verified" ? "good" : "warn"}>
                      Payment {tx.payment_status}
                    </Chip>
                    <Chip>Stock {tx.stock_status}</Chip>
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}

        {ledger && (
          <section className="mt-12 grid gap-6">
            <div className="glass rounded-3xl p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="section-title text-2xl">Shared Proof Ledger</h2>
                <div className="flex gap-2">
                  <button
                    className="rounded-full border border-ink px-4 py-2"
                    onClick={() => pollStatus(activeTxId)}
                  >
                    Sync Status
                  </button>
                  <button
                    className="rounded-full border border-ink px-4 py-2"
                    onClick={() => downloadLedgerPdf(activeTxId)}
                  >
                    Download Bill PDF
                  </button>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2 text-sm">
                <div className="rounded-2xl border border-slate/20 p-4">Buyer: {ledger.buyer}</div>
                <div className="rounded-2xl border border-slate/20 p-4">Seller: {ledger.seller}</div>
                <div className="rounded-2xl border border-slate/20 p-4">Item: {ledger.item}</div>
                <div className="rounded-2xl border border-slate/20 p-4">Qty: {ledger.quantity}</div>
                <div className="rounded-2xl border border-slate/20 p-4">Unit Price: ₹{ledger.unit_price}</div>
                <div className="rounded-2xl border border-slate/20 p-4">Payment: {ledger.payment_status}</div>
                <div className="rounded-2xl border border-slate/20 p-4">
                  Razorpay Order: {ledger.razorpay_order_id || "-"}
                </div>
                <div className="rounded-2xl border border-slate/20 p-4">
                  Razorpay Payment: {ledger.razorpay_payment_id || "-"}
                </div>
                <div className="rounded-2xl border border-slate/20 p-4">Stock: {ledger.stock_status}</div>
                <div className="rounded-2xl border border-slate/20 p-4">
                  Market: {ledger.market_low && ledger.market_high ? `₹${ledger.market_low} - ₹${ledger.market_high}` : "-"}
                </div>
              </div>
            </div>

            <div className="glass rounded-3xl p-6">
              <h2 className="section-title text-2xl">Open Dispute</h2>
              <form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={handleCreateDispute}>
                <input className="rounded-2xl border border-slate/30 p-3" value={activeTxId} readOnly />
                <input className="rounded-2xl border border-slate/30 p-3" name="reason" placeholder="Reason" required />
                <button className="rounded-full bg-ink text-white px-5 py-2 md:col-span-2">
                  Open Dispute
                </button>
              </form>
            </div>
          </section>
        )}

        {user && user.role === "admin" && (
          <section className="mt-12 grid gap-6">
            <div className="glass rounded-3xl p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="section-title text-2xl">Admin Console</h2>
                <div className="flex gap-2">
                  <button
                    className="rounded-full border border-ink px-3 py-1 text-sm"
                    onClick={() => setMessage(`Config saved: ${JSON.stringify(adminConfig)}`)}
                  >
                    Save config
                  </button>
                </div>
              </div>
              <div className="mt-4 md:grid md:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-slate/20 p-4">
                  <div className="font-semibold">Customer Details</div>
                  <div className="text-xs text-slate">List of all users by role.</div>
                  <div className="mt-2 text-sm">
                    {adminUsers.filter((u) => u.role === "buyer").length} buyers
                  </div>
                  {adminUsers.filter((u) => u.role === "buyer").slice(0, 3).map((u) => (
                    <div key={u.id} className="py-1 text-sm border-b border-slate/10">
                      {u.name} ({u.email})
                    </div>
                  ))}
                </div>
                <div className="rounded-2xl border border-slate/20 p-4">
                  <div className="font-semibold">Seller Details</div>
                  <div className="text-xs text-slate">Active sellers and items in inventory.</div>
                  <div className="mt-2 text-sm">
                    {adminUsers.filter((u) => u.role === "seller").length} sellers
                  </div>
                  {adminUsers.filter((u) => u.role === "seller").slice(0, 3).map((u) => (
                    <div key={u.id} className="py-1 text-sm border-b border-slate/10">
                      {u.name} ({u.email})
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="glass rounded-3xl p-6">
              <h2 className="section-title text-2xl">Configuration</h2>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div>
                  <label className="block text-sm font-medium mb-1">Site title</label>
                  <input
                    className="rounded-2xl border border-slate/30 p-2 w-full"
                    value={adminConfig.siteTitle}
                    onChange={(e) => setAdminConfig({ ...adminConfig, siteTitle: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Require admin invite</label>
                  <select
                    className="rounded-2xl border border-slate/30 p-2 w-full"
                    value={adminConfig.requireAdminInvite ? "yes" : "no"}
                    onChange={(e) => setAdminConfig({ ...adminConfig, requireAdminInvite: e.target.value === "yes" })}
                  >
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Allow guest inventory view</label>
                  <select
                    className="rounded-2xl border border-slate/30 p-2 w-full"
                    value={adminConfig.allowGuestView ? "yes" : "no"}
                    onChange={(e) => setAdminConfig({ ...adminConfig, allowGuestView: e.target.value === "yes" })}
                  >
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="glass rounded-3xl p-6">
              <h2 className="section-title text-2xl">Admin Transactions + Ledger</h2>
              <div className="mt-4 grid gap-3">
                {adminTransactions.map((tx) => (
                  <button
                    key={tx.id}
                    className={`text-left rounded-2xl border p-4 text-sm transition ${
                      activeTxId === tx.id ? "border-ink shadow-glow" : "border-slate/20"
                    }`}
                    onClick={() => handleLedgerLookup(tx.id)}
                  >
                    <div className="font-semibold">{tx.item_name}</div>
                    <div className="text-slate">Buyer: {tx.buyer_name} | Seller: {tx.seller_name}</div>
                    <div className="mt-1">₹{tx.unit_price} × {tx.quantity} | {tx.payment_status}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="glass rounded-3xl p-6">
              <h2 className="section-title text-2xl">Admin Disputes</h2>
              <div className="mt-4 grid gap-3">
                {disputes.map((dispute) => (
                  <div key={dispute.id} className="rounded-2xl border border-slate/20 p-4 text-sm">
                    <div className="flex flex-wrap justify-between gap-2">
                      <span className="font-semibold">{dispute.id}</span>
                      <Chip>{dispute.status}</Chip>
                    </div>
                    <div className="mt-2 text-slate">
                      Buyer: {dispute.buyer_name} | Seller: {dispute.seller_name}
                    </div>
                    <div className="mt-2">{dispute.reason}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="glass rounded-3xl p-6">
              <h2 className="section-title text-2xl">Resolve Dispute</h2>
              <form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={handleResolveDispute}>
                <select className="rounded-2xl border border-slate/30 p-3" name="dispute_id" required>
                  <option value="">Select dispute</option>
                  {disputes.map((dispute) => (
                    <option key={dispute.id} value={dispute.id}>
                      {dispute.id} | {dispute.status}
                    </option>
                  ))}
                </select>
                <select className="rounded-2xl border border-slate/30 p-3" name="status" required>
                  <option value="resolved">Resolved</option>
                  <option value="rejected">Rejected</option>
                </select>
                <input
                  className="rounded-2xl border border-slate/30 p-3 md:col-span-2"
                  name="resolution_note"
                  placeholder="Resolution note"
                  required
                />
                <button className="rounded-full bg-ink text-white px-5 py-2 md:col-span-2">
                  Resolve
                </button>
              </form>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
