"""Utilidades compartidas por los tests del formulario de tratamiento."""


def formset_data(lines, initial=0, prefix="treatmentproduct_set"):
    """
    Construye el bloque del formset de productos.
    lines: lista de dicts {product, dose, total_dose, id?, delete?, total_overridden?}
    """
    data = {
        f"{prefix}-TOTAL_FORMS": str(len(lines)),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "1",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }
    for i, line in enumerate(lines):
        p = f"{prefix}-{i}-"
        data[p + "id"] = str(line.get("id", ""))
        data[p + "product"] = str(line["product"])
        data[p + "dose"] = line["dose"]
        data[p + "total_dose"] = line.get("total_dose", "")
        data[p + "DELETE"] = "on" if line.get("delete") else ""
        if "total_overridden" in line:
            data[p + "total_overridden"] = line["total_overridden"]
        if "position" in line:
            data[p + "position"] = str(line["position"])
    return data
