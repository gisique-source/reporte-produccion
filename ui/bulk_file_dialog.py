"""Diálogo de carga masiva desde archivo Excel (.xlsx / .xlsm)."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from bulk_import import FilaImport, crear_maestros_faltantes, fila_a_datos, maestros_faltantes
from catalog import ETIQUETAS
from db import PesajeDatabase, format_fecha_editable, nombre_mes
from excel_import import (
    DiaExcel,
    LibroExcelImport,
    leer_libro_excel,
    validar_dia_en_mes,
)
from import_validator import (
    EstadoImport,
    FilaValidada,
    resumir_validacion,
    validar_filas_importacion,
)
from ui.widgets import Theme, secondary_button


class BulkFileDialog(tk.Toplevel):
    """
    Vista previa por días del libro mensual:
    - Selector de mes/año (prellenado desde archivo)
    - Checklist de días con datos
    - Alerta si el día no existe en ese mes (p. ej. 31 en febrero)
    """

    def __init__(
        self,
        master: tk.Widget,
        db: PesajeDatabase,
        path: str,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        self.db = db
        self.path = path
        self.on_done = on_done
        self.title("Carga masiva desde Excel")
        self.configure(bg=Theme.BG)
        self.geometry("1080x640")
        self.minsize(900, 520)
        self.transient(master.winfo_toplevel())
        self.grab_set()

        self.var_info = tk.StringVar()
        self.var_alertas = tk.StringVar()
        self.var_falt = tk.StringVar()
        self.var_preview = tk.StringVar(value="Seleccione uno o más días.")

        try:
            self.libro: LibroExcelImport = leer_libro_excel(path, db.catalogo)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Excel",
                f"No se pudo leer el archivo:\n{exc}",
                parent=master,
            )
            self.after(10, self.destroy)
            return

        self.var_anio = tk.IntVar(value=self.libro.anio_sugerido)
        self.var_mes = tk.IntVar(value=self.libro.mes_sugerido)
        self._checks: dict[int, tk.BooleanVar] = {}
        self._dia_labels: dict[int, tk.Label] = {}
        self._validadas: list[FilaValidada] = []

        self._build()
        self._aplicar_periodo()
        self.bind("<Escape>", lambda _e: self.destroy())

    def _build(self) -> None:
        tk.Label(
            self,
            text="Archivo Excel → vista previa por días",
            font=("Segoe UI", 13, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(pady=(10, 2))
        tk.Label(
            self,
            textvariable=self.var_info,
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
            wraplength=1000,
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=12)

        # Período
        bar = tk.Frame(self, bg=Theme.PANEL, padx=10, pady=8)
        bar.pack(fill=tk.X, padx=12, pady=6)
        tk.Label(bar, text="Período del archivo", fg=Theme.FG, bg=Theme.PANEL).pack(
            side=tk.LEFT
        )
        tk.Label(bar, text="Mes", fg=Theme.MUTED, bg=Theme.PANEL).pack(
            side=tk.LEFT, padx=(16, 4)
        )
        meses = [f"{i:02d} — {nombre_mes(i)}" for i in range(1, 13)]
        self.cb_mes = ttk.Combobox(
            bar, values=meses, state="readonly", width=18
        )
        self.cb_mes.current(self.var_mes.get() - 1)
        self.cb_mes.pack(side=tk.LEFT)
        self.cb_mes.bind("<<ComboboxSelected>>", self._on_mes_change)

        tk.Label(bar, text="Año", fg=Theme.MUTED, bg=Theme.PANEL).pack(
            side=tk.LEFT, padx=(12, 4)
        )
        sp = tk.Spinbox(
            bar,
            from_=2020,
            to=2100,
            textvariable=self.var_anio,
            width=6,
            command=self._aplicar_periodo,
        )
        sp.pack(side=tk.LEFT)
        sp.bind("<Return>", lambda _e: self._aplicar_periodo())
        sp.bind("<FocusOut>", lambda _e: self._aplicar_periodo())

        secondary_button(bar, "Aplicar período", self._aplicar_periodo).pack(
            side=tk.LEFT, padx=10
        )
        secondary_button(bar, "Marcar días con datos", self._marcar_con_datos).pack(
            side=tk.LEFT, padx=4
        )
        secondary_button(bar, "Ninguno", self._marcar_ninguno).pack(side=tk.LEFT, padx=4)

        tk.Label(
            self,
            textvariable=self.var_alertas,
            font=("Segoe UI", 9, "bold"),
            fg=Theme.ERR_COLOR,
            bg=Theme.BG,
            wraplength=1000,
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=12)

        body = tk.Frame(self, bg=Theme.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        # Lista de días
        left = tk.Frame(body, bg=Theme.PANEL, padx=8, pady=8)
        left.pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(
            left,
            text="Días del mes",
            font=("Segoe UI", 10, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.PANEL,
        ).pack(anchor="w")

        canvas = tk.Canvas(left, bg=Theme.PANEL, highlightthickness=0, width=280)
        sy = ttk.Scrollbar(left, orient=tk.VERTICAL, command=canvas.yview)
        self.days_frame = tk.Frame(canvas, bg=Theme.PANEL)
        self.days_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.days_frame, anchor="nw")
        canvas.configure(yscrollcommand=sy.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        for d in self.libro.dias:
            row = tk.Frame(self.days_frame, bg=Theme.PANEL)
            row.pack(fill=tk.X, pady=1)
            var = tk.BooleanVar(value=d.n_filas > 0)
            self._checks[d.dia] = var
            cb = tk.Checkbutton(
                row,
                variable=var,
                bg=Theme.PANEL,
                activebackground=Theme.PANEL,
                command=self._on_check,
            )
            cb.pack(side=tk.LEFT)
            lbl = tk.Label(
                row,
                text=self._texto_dia(d),
                font=("Segoe UI", 9),
                fg=Theme.FG,
                bg=Theme.PANEL,
                anchor="w",
            )
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._dia_labels[d.dia] = lbl

        # Preview
        right = tk.Frame(body, bg=Theme.BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        tk.Label(
            right,
            textvariable=self.var_preview,
            font=("Segoe UI", 10, "bold"),
            fg=Theme.FG,
            bg=Theme.BG,
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            right,
            textvariable=self.var_falt,
            font=("Segoe UI", 9),
            fg=Theme.US_COLOR,
            bg=Theme.BG,
            wraplength=700,
            justify=tk.LEFT,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 4))

        wrap = tk.Frame(right, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        style = ttk.Style(self)
        style.configure(
            "BulkFile.Treeview",
            background=Theme.TREE_BG,
            foreground=Theme.FG,
            fieldbackground=Theme.TREE_BG,
            rowheight=22,
            font=("Segoe UI", 9),
        )
        style.configure(
            "BulkFile.Treeview.Heading",
            background=Theme.TREE_HEAD,
            foreground=Theme.TREE_HEAD_FG,
            font=("Segoe UI", 9, "bold"),
        )
        cols = (
            "dia",
            "ok",
            "fardo",
            "cliente",
            "lote",
            "color",
            "dn",
            "corte",
            "total",
            "bruto",
            "neto",
            "operario",
        )
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", style="BulkFile.Treeview"
        )
        heads = {
            "dia": ("Día", 40),
            "ok": ("Estado", 90),
            "fardo": ("Fardo", 50),
            "cliente": ("Cliente", 130),
            "lote": ("Lote", 90),
            "color": ("Color", 90),
            "dn": ("Dn", 45),
            "corte": ("Corte", 50),
            "total": ("Total", 65),
            "bruto": ("Bruto", 65),
            "neto": ("Neto", 65),
            "operario": ("Op.", 80),
        }
        for k, (t, w) in heads.items():
            self.tree.heading(k, text=t)
            self.tree.column(k, width=w, anchor="center")
        self.tree.tag_configure("ok", foreground=Theme.ST_COLOR)
        self.tree.tag_configure("faltante", foreground="#ff9f43")
        self.tree.tag_configure("error", foreground=Theme.ERR_COLOR)
        self.tree.tag_configure("modificar", foreground=Theme.US_COLOR)
        self.tree.tag_configure("ya", foreground=Theme.MUTED)
        self.tree.tag_configure(
            "sep",
            foreground=Theme.ACCENT,
            font=("Segoe UI", 9, "bold"),
        )

        sy2 = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy2.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy2.pack(side=tk.RIGHT, fill=tk.Y)

        btns = tk.Frame(self, bg=Theme.BG)
        btns.pack(fill=tk.X, padx=12, pady=10)
        secondary_button(
            btns, "Crear maestros faltantes", self._crear_faltantes
        ).pack(side=tk.LEFT, padx=4)
        secondary_button(
            btns, "Importar pendientes / cambios", self._importar
        ).pack(side=tk.LEFT, padx=4)
        secondary_button(btns, "Cancelar", self.destroy).pack(side=tk.RIGHT, padx=4)

    def _texto_dia(self, d: DiaExcel) -> str:
        return (
            f"Día {d.dia:02d}  ·  {d.n_filas} fila(s)  ·  "
            f"OK {d.n_ok} / falt {d.n_faltantes} / err {d.n_errores}"
        )

    def _on_mes_change(self, _event=None) -> None:
        self.var_mes.set(self.cb_mes.current() + 1)
        self._aplicar_periodo()

    def _marcar_con_datos(self) -> None:
        for d in self.libro.dias:
            self._checks[d.dia].set(d.n_filas > 0)
        self._on_check()

    def _marcar_ninguno(self) -> None:
        for var in self._checks.values():
            var.set(False)
        self._on_check()

    def _aplicar_periodo(self) -> None:
        anio = int(self.var_anio.get())
        mes = int(self.var_mes.get())
        max_d = calendar.monthrange(anio, mes)[1]
        n_datos = sum(1 for d in self.libro.dias if d.n_filas)
        n_filas = sum(d.n_filas for d in self.libro.dias)
        self.var_info.set(
            f"{self.path}\n"
            f"Período: {nombre_mes(mes)} {anio} ({max_d} días) · "
            f"detectado por {self.libro.origen_periodo or 'manual'} · "
            f"{n_datos} día(s) con datos · {n_filas} fardo(s)"
        )

        alertas = list(self.libro.alertas)
        for d in self.libro.dias:
            if d.n_filas == 0:
                continue
            msg = validar_dia_en_mes(anio, mes, d.dia)
            if msg:
                alertas.append(f"Día {d.dia:02d}: {msg}")
            lbl = self._dia_labels.get(d.dia)
            if lbl:
                if msg:
                    lbl.config(fg=Theme.ERR_COLOR, text=self._texto_dia(d) + "  ⚠ inválido")
                    self._checks[d.dia].set(False)
                else:
                    lbl.config(fg=Theme.FG, text=self._texto_dia(d))

        # Dedup
        seen: set[str] = set()
        uniq: list[str] = []
        for a in alertas:
            if a not in seen:
                seen.add(a)
                uniq.append(a)
        if uniq:
            self.var_alertas.set("⚠ " + " | ".join(uniq[:6]) + (" …" if len(uniq) > 6 else ""))
        else:
            self.var_alertas.set("")

        self._on_check()

    def _dias_seleccionados(self) -> list[DiaExcel]:
        anio = int(self.var_anio.get())
        mes = int(self.var_mes.get())
        out: list[DiaExcel] = []
        for d in self.libro.dias:
            if not self._checks[d.dia].get():
                continue
            if validar_dia_en_mes(anio, mes, d.dia):
                continue
            if d.n_filas == 0:
                continue
            out.append(d)
        return out

    def _filas_seleccionadas(self) -> list[tuple[date, FilaImport]]:
        anio = int(self.var_anio.get())
        mes = int(self.var_mes.get())
        pares: list[tuple[date, FilaImport]] = []
        for d in self._dias_seleccionados():
            dia_fecha = date(anio, mes, d.dia)
            for f in d.filas:
                pares.append((dia_fecha, f))
        return pares

    def _on_check(self) -> None:
        pares = self._filas_seleccionadas()
        filas = [f for _, f in pares]
        self._validadas = validar_filas_importacion(
            pares, self.db.obtener_por_lote_fardo
        )
        res = resumir_validacion(self._validadas)
        dias_n = len({d for d, _ in pares})
        pendientes = res["nuevo"] + res["modificar"]
        self.var_preview.set(
            f"Vista previa · {dias_n} día(s) · {len(filas)} fila(s)  ·  "
            f"Nuevos {res['nuevo']} · Modificar {res['modificar']} · "
            f"Ya subidos {res['ya_subido']} · "
            f"Maestros {res['faltante']} · Errores {res['error']}"
        )

        falt = maestros_faltantes(filas)
        partes = []
        for tipo, vals in falt.items():
            if vals:
                partes.append(
                    f"{ETIQUETAS[tipo]}: {', '.join(vals[:6])}"
                    + ("…" if len(vals) > 6 else "")
                )
        hint = (
            f"Se importarán solo pendientes ({pendientes}). "
            "Los ya subidos (fila idéntica) se listan abajo y se omiten."
        )
        if partes:
            self.var_falt.set(hint + "\nFaltan maestros → " + " | ".join(partes))
        else:
            self.var_falt.set(hint)

        self.tree.delete(*self.tree.get_children())

        pendientes_v = [v for v in self._validadas if v.estado != EstadoImport.YA_SUBIDO]
        ya_v = [v for v in self._validadas if v.estado == EstadoImport.YA_SUBIDO]

        if pendientes_v:
            self.tree.insert(
                "",
                tk.END,
                iid="sep_pend",
                values=(
                    "",
                    f"—— Pendientes ({len(pendientes_v)}) ——",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ),
                tags=("sep",),
            )
            for i, v in enumerate(pendientes_v):
                self._insertar_fila_tree(f"p{i}", v)

        if ya_v:
            self.tree.insert(
                "",
                tk.END,
                iid="sep_ya",
                values=(
                    "",
                    f"—— Ya subidos ({len(ya_v)}) ——",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ),
                tags=("sep",),
            )
            for i, v in enumerate(ya_v):
                self._insertar_fila_tree(f"y{i}", v)

    def _insertar_fila_tree(self, iid: str, v: FilaValidada) -> None:
        f = v.fila
        if v.estado == EstadoImport.ERROR:
            tag = "error"
        elif v.estado == EstadoImport.FALTANTE:
            tag = "faltante"
        elif v.estado == EstadoImport.MODIFICAR:
            tag = "modificar"
        elif v.estado == EstadoImport.YA_SUBIDO:
            tag = "ya"
        else:
            tag = "ok"

        def mark(ok: Optional[str], raw: str) -> str:
            if not raw:
                return ""
            return raw if ok else f"⚠ {raw}"

        self.tree.insert(
            "",
            tk.END,
            iid=iid,
            values=(
                format_fecha_editable(v.dia),
                v.etiqueta,
                f.nro_fardo,
                mark(f.cliente_ok, f.cliente),
                f.lote,
                mark(f.color_ok, f.color),
                mark(f.dn_ok, f.dn),
                mark(f.corte_ok, f.corte),
                f"{f.peso_total:.2f}",
                f"{f.peso_bruto:.2f}",
                f"{f.peso_neto:.2f}",
                f.operario,
            ),
            tags=(tag,),
        )

    def _crear_faltantes(self) -> None:
        filas = [f for _, f in self._filas_seleccionadas()]
        falt = maestros_faltantes(filas)
        total = sum(len(v) for v in falt.values())
        if total == 0:
            messagebox.showinfo("Excel", "No hay maestros faltantes en la selección.")
            return
        detalle = "\n".join(
            f"· {ETIQUETAS[t]}: {', '.join(vs[:12])}" for t, vs in falt.items() if vs
        )
        if not messagebox.askyesno(
            "Crear maestros",
            f"Se crearán {total} valor(es):\n\n{detalle}\n\n¿Continuar?",
        ):
            return
        n = crear_maestros_faltantes(self.db.catalogo, filas)
        # Re-parsear para refrescar resolución en todos los días del libro
        try:
            self.libro = leer_libro_excel(self.path, self.db.catalogo)
        except Exception:  # noqa: BLE001
            pass
        for d in self.libro.dias:
            if d.dia in self._dia_labels:
                self._dia_labels[d.dia].config(text=self._texto_dia(d))
        self._aplicar_periodo()
        messagebox.showinfo("Excel", f"Creados / reactivados: {n}")

    def _importar(self) -> None:
        anio = int(self.var_anio.get())
        mes = int(self.var_mes.get())
        seleccion = self._dias_seleccionados()
        if not seleccion:
            messagebox.showwarning(
                "Excel",
                "Marque al menos un día válido con datos.\n"
                "Los días inexistentes en el mes (p. ej. 31 en febrero) se omiten.",
            )
            return

        invalidos = []
        for d in self.libro.dias:
            if self._checks[d.dia].get() and validar_dia_en_mes(anio, mes, d.dia):
                invalidos.append(d.dia)
        if invalidos:
            messagebox.showwarning(
                "Días inválidos",
                f"Estos días no existen en {nombre_mes(mes)} {anio} y no se importarán:\n"
                f"{', '.join(f'{x:02d}' for x in invalidos)}",
            )

        # Revalidar por si cambió el período
        self._validadas = validar_filas_importacion(
            self._filas_seleccionadas(), self.db.obtener_por_lote_fardo
        )
        aplicar = [v for v in self._validadas if v.se_puede_aplicar]
        ya = sum(1 for v in self._validadas if v.estado == EstadoImport.YA_SUBIDO)
        bloqueados = sum(
            1
            for v in self._validadas
            if v.estado in (EstadoImport.FALTANTE, EstadoImport.ERROR)
        )
        n_nuevos = sum(1 for v in aplicar if v.estado == EstadoImport.NUEVO)
        n_mod = sum(1 for v in aplicar if v.estado == EstadoImport.MODIFICAR)

        if not aplicar:
            if ya and not bloqueados:
                messagebox.showinfo(
                    "Excel",
                    f"Nada que importar: las {ya} fila(s) seleccionada(s) "
                    "ya están en la base con los mismos datos.",
                )
            else:
                messagebox.showwarning(
                    "Excel",
                    "No hay filas listas. Cree maestros faltantes o corrija errores.",
                )
            return

        msg = (
            f"Aplicar en {nombre_mes(mes)} {anio}:\n"
            f"· Nuevos: {n_nuevos}\n"
            f"· Modificar existentes: {n_mod}\n"
        )
        if ya:
            msg += f"· Ya subidos (se omiten): {ya}\n"
        if bloqueados:
            msg += f"· Omitidos por faltantes/errores: {bloqueados}\n"
        msg += "\n¿Continuar?"
        if not messagebox.askyesno("Importar Excel", msg):
            return

        ok_ins = 0
        ok_upd = 0
        errores = 0
        for v in aplicar:
            try:
                datos = fila_a_datos(v.fila, v.dia)
                if v.estado == EstadoImport.NUEVO:
                    self.db.insertar(
                        datos, fecha_hora=datos.fecha_hora_registro or None
                    )
                    ok_ins += 1
                elif v.estado == EstadoImport.MODIFICAR and v.registro_id is not None:
                    self.db.actualizar(v.registro_id, datos)
                    # Si el Excel trae otra fecha, actualizar timestamp
                    if datos.fecha_hora_registro:
                        self._actualizar_fecha_hora(
                            v.registro_id, datos.fecha_hora_registro
                        )
                    ok_upd += 1
            except Exception:  # noqa: BLE001
                errores += 1

        messagebox.showinfo(
            "Excel",
            f"Insertados: {ok_ins}  ·  Actualizados: {ok_upd}"
            + (f"  ·  Fallidos: {errores}" if errores else "")
            + (f"  ·  Omitidos ya subidos: {ya}" if ya else ""),
        )
        if self.on_done:
            self.on_done()
        self.destroy()

    def _actualizar_fecha_hora(self, registro_id: int, fecha_hora: str) -> None:
        """Ajusta fecha_hora tras actualizar datos (no expuesto en actualizar())."""
        try:
            with self.db._lock:
                with self.db._connect() as conn:
                    conn.execute(
                        """
                        UPDATE pesajes
                        SET fecha_hora = ?, estado_sincronizado = 0
                        WHERE id = ?
                        """,
                        (fecha_hora, registro_id),
                    )
                    conn.commit()
        except Exception:  # noqa: BLE001
            pass
