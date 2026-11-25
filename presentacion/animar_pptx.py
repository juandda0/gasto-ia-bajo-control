"""Agrega transiciones y animaciones (entradas, salidas y barridos) a la presentación.

pptxgenjs no escribe animaciones, así que este script toma animaciones.json
(generado por generar_pptx.js) y escribe el <p:timing> de cada diapositiva.

Uso: python animar_pptx.py gasto-ia-bajo-control.pptx animaciones.json
"""
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ENTRADAS = {
    # efecto: (presetID, presetSubtype, filtro, duración en ms)
    "fade": (10, 0, "fade", 500),
    "wipeup": (22, 4, "wipe(up)", 600),
    "wiperight": (22, 8, "wipe(right)", 600),
}


class Ids:
    def __init__(self):
        self.n = 2  # 1 = raíz, 2 = secuencia principal

    def next(self):
        self.n += 1
        return self.n


def efecto(ids, spid, eff, delay, node_type):
    if eff == "out":
        return (
            f'<p:par><p:cTn id="{ids.next()}" presetID="10" presetClass="exit" presetSubtype="0" fill="hold" grpId="1" nodeType="{node_type}">'
            f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>'
            f'<p:animEffect transition="out" filter="fade"><p:cBhvr><p:cTn id="{ids.next()}" dur="400"/>'
            f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>'
            f'<p:set><p:cBhvr><p:cTn id="{ids.next()}" dur="1" fill="hold"><p:stCondLst><p:cond delay="399"/></p:stCondLst></p:cTn>'
            f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>'
            f'<p:to><p:strVal val="hidden"/></p:to></p:set>'
            f'</p:childTnLst></p:cTn></p:par>'
        )
    preset, sub, filtro, dur = ENTRADAS[eff]
    return (
        f'<p:par><p:cTn id="{ids.next()}" presetID="{preset}" presetClass="entr" presetSubtype="{sub}" fill="hold" grpId="0" nodeType="{node_type}">'
        f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>'
        f'<p:set><p:cBhvr><p:cTn id="{ids.next()}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>'
        f'<p:to><p:strVal val="visible"/></p:to></p:set>'
        f'<p:animEffect transition="in" filter="{filtro}"><p:cBhvr><p:cTn id="{ids.next()}" dur="{dur}"/>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>'
        f'</p:childTnLst></p:cTn></p:par>'
    )


def timing(grupos, ids_por_nombre):
    ids = Ids()
    pars, bld = [], {}
    for k, g in enumerate(grupos):
        if not g["items"]:
            continue
        auto = g["trigger"] == "auto" and k == 0
        efectos = []
        for n, it in enumerate(g["items"]):
            spid = ids_por_nombre[it["name"]]
            tipo = ("afterEffect" if auto else "clickEffect") if n == 0 else "withEffect"
            efectos.append(efecto(ids, spid, it["eff"], it["delay"], tipo))
            bld[(spid, 1 if it["eff"] == "out" else 0)] = True
        cond = '<p:cond delay="indefinite"/>' + ('<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond>' if auto else "")
        pars.append(
            f'<p:par><p:cTn id="{ids.next()}" fill="hold"><p:stCondLst>{cond}</p:stCondLst><p:childTnLst>'
            f'<p:par><p:cTn id="{ids.next()}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
            + "".join(efectos)
            + "</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>"
        )
    if not pars:
        return ""
    bld_xml = "".join(f'<p:bldP spid="{spid}" grpId="{grp}" animBg="1"/>' for spid, grp in bld)
    return (
        '<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
        '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
        + "".join(pars)
        + '</p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>'
        "</p:childTnLst></p:cTn></p:par></p:tnLst>"
        f"<p:bldLst>{bld_xml}</p:bldLst></p:timing>"
    )


TRANSICION = '<p:transition spd="med"><p:fade/></p:transition>'


def main(pptx, spec_path):
    spec = json.loads(Path(spec_path).read_text())
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(pptx) as z:
            z.extractall(tmp)
            orden = z.namelist()
        for num, grupos in spec.items():
            ruta = Path(tmp, "ppt", "slides", f"slide{num}.xml")
            xml = ruta.read_text(encoding="utf-8")
            ids = {m.group(2): m.group(1) for m in re.finditer(r'<p:cNvPr id="(\d+)" name="([^"]+)"', xml)}
            faltan = {it["name"] for g in grupos for it in g["items"]} - ids.keys()
            if faltan:
                raise SystemExit(f"slide{num}: no encuentro {sorted(faltan)}")
            extra = TRANSICION + timing(grupos, ids)
            if "</p:clrMapOvr>" in xml:
                xml = xml.replace("</p:clrMapOvr>", "</p:clrMapOvr>" + extra, 1)
            else:
                xml = xml.replace("</p:cSld>", "</p:cSld>" + extra, 1)
            ruta.write_text(xml, encoding="utf-8")
        salida = Path(pptx).with_suffix(".tmp.pptx")
        with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
            for nombre in orden:
                if not nombre.endswith("/"):  # sin entradas de carpeta: fallan al abrir desde la nube
                    z.write(Path(tmp, nombre), nombre)
        shutil.move(salida, pptx)
    print("animaciones agregadas a", pptx)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
