"""Prosecutor — raise charges for raw field inequalities."""

from __future__ import annotations

from harbormaster.models import Charge, ExtractedDocument, FieldValue


def _norm(v: str) -> str:
    return " ".join(v.strip().upper().split())


class Prosecutor:
    def file_charges(
        self,
        left_doc: ExtractedDocument,
        right_doc: ExtractedDocument,
        fields: list[str] | None = None,
    ) -> list[Charge]:
        keys = fields or sorted(set(left_doc.fields) | set(right_doc.fields))
        charges: list[Charge] = []
        consignee_left = left_doc.fields.get("consignee")
        consignee_right = right_doc.fields.get("consignee")

        for name in keys:
            lv = left_doc.fields.get(name)
            rv = right_doc.fields.get(name)
            if lv is None or rv is None:
                continue
            if _norm(lv.raw_value) == _norm(rv.raw_value):
                continue
            note = "raw inequality"
            if name == "notify_party":
                bits = []
                if consignee_left:
                    bits.append(f"consignee_left={consignee_left.raw_value}")
                if consignee_right:
                    bits.append(f"consignee_right={consignee_right.raw_value}")
                if bits:
                    note = "|".join(bits)
                elif consignee_left or consignee_right:
                    c = consignee_left or consignee_right
                    note = f"consignee={c.raw_value}"
            charges.append(Charge(field=name, left=lv, right=rv, note=note))
        return charges

    def charge_pair(self, field: str, left: FieldValue, right: FieldValue, note: str = "") -> Charge:
        return Charge(field=field, left=left, right=right, note=note or "raw inequality")
