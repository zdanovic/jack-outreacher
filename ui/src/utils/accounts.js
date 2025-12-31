export const accountKey = (acc) => {
  if (!acc) return "";
  return String(acc.public_id || acc.id || "");
};

export const accountDisplayId = (acc) => {
  if (!acc) return "";
  return String(acc.display_id || acc.public_id || acc.id || "");
};

export const accountPhoneTail = (acc) => {
  const digits = String(acc?.phone || "").replace(/\D/g, "");
  return digits ? digits.slice(-4) : "";
};

export const eventAccountId = (event) => {
  if (!event) return "";
  return String(event.account_public_id || event.account_id || "");
};

export const leadAccountId = (lead) => {
  if (!lead) return "";
  return String(lead.last_account_public_id || lead.last_account_id || "");
};
