import sqlite3
from datetime import date, datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Controle de Gastos Leve", page_icon="💳")

conn = sqlite3.connect("gastos.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS bancos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT UNIQUE NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS transacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data DATE NOT NULL,
    banco_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    valor REAL NOT NULL,
    descricao TEXT,
    FOREIGN KEY (banco_id) REFERENCES bancos (id)
)
""")
conn.commit()

st.title("💳 Registro Rápido de Gastos")

aba1, aba2, aba3 = st.tabs(
    ["📝 Registrar Gasto", "📅 Resumo Mensal", "🏦 Gerenciar Bancos"]
)

# --- ABA 3: GERENCIAR BANCOS ---
with aba3:
    st.subheader("Cadastrar Novo Banco/Cartão")
    novo_banco = st.text_input("Nome do Banco ou Cartão").strip()
    if st.button("Adicionar Banco"):
        if novo_banco:
            try:
                cursor.execute(
                    "INSERT INTO bancos (nome) VALUES (?)", (novo_banco,)
                )
                conn.commit()
                st.success(f"Banco '{novo_banco}' adicionado com sucesso!")
            except sqlite3.IntegrityError:
                st.warning("Este banco já está cadastrado.")
        else:
            st.error("Informe um nome válido.")

bancos_df = pd.read_sql_query("SELECT id, nome FROM bancos", conn)

# --- ABA 1: REGISTRAR GASTO ---
with aba1:
    if bancos_df.empty:
        st.info(
            "Nenhum banco cadastrado ainda. Vá na aba 'Gerenciar Bancos' para adicionar o primeiro."
        )
    else:
        st.subheader("Novo Lançamento")
        with st.form("form_transacao", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                banco_selecionado = st.selectbox(
                    "Selecione o Banco",
                    options=bancos_df["nome"].tolist(),
                )
                tipo = st.radio(
                    "Tipo de Pagamento",
                    ["Débito", "Crédito"],
                    horizontal=True,
                )
            with col2:
                valor = st.number_input(
                    "Valor (R$)", min_value=0.01, format="%.2f"
                )
                data_gasto = st.date_input("Data", value=date.today())

            descricao = st.text_input("Descrição (Opcional)")
            submitted = st.form_submit_button("Registrar Gasto")

            if submitted:
                banco_id = int(
                    bancos_df[bancos_df["nome"] == banco_selecionado][
                        "id"
                    ].values[0]
                )
                cursor.execute(
                    "INSERT INTO transacoes (data, banco_id, tipo, valor, descricao) VALUES (?, ?, ?, ?, ?)",
                    (
                        data_gasto.strftime("%Y-%m-%d"),
                        banco_id,
                        tipo,
                        valor,
                        descricao,
                    ),
                )
                conn.commit()
                st.success("Gasto registrado com sucesso!")

    st.divider()
    st.subheader("📊 Resumo do Dia")
    data_filtro = st.date_input("Filtrar por data", value=date.today())

    query_dia = """
    SELECT t.id, t.data, b.nome AS banco, t.tipo, t.valor, t.descricao
    FROM transacoes t
    JOIN bancos b ON t.banco_id = b.id
    WHERE t.data = ?
    """
    df_dia = pd.read_sql_query(
        query_dia, conn, params=(data_filtro.strftime("%Y-%m-%d"),)
    )

    if not df_dia.empty:
        total_debito_dia = df_dia[df_dia["tipo"] == "Débito"]["valor"].sum()
        total_credito_dia = df_dia[df_dia["tipo"] == "Crédito"]["valor"].sum()

        col_deb, col_cred, col_tot = st.columns(3)
        col_deb.metric("Total Débito", f"R$ {total_debito_dia:.2f}")
        col_cred.metric("Total Crédito", f"R$ {total_credito_dia:.2f}")
        col_tot.metric(
            "Total do Dia", f"R$ {(total_debito_dia + total_credito_dia):.2f}"
        )

        st.dataframe(
            df_dia[["banco", "tipo", "valor", "descricao"]],
            use_container_width=True,
        )
    else:
        st.info("Nenhum registro encontrado para esta data.")

# --- ABA 2: RESUMO MENSAL ---
with aba2:
    st.subheader("🗓️ Gastos do Mês")

    col_m, col_a = st.columns(2)
    mes_atual = datetime.now().month
    ano_atual = datetime.now().year

    meses = [
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]

    mes_nome = col_m.selectbox(
        "Mês", meses, index=mes_atual - 1, key="select_mes"
    )
    mes_num = meses.index(mes_nome) + 1
    ano_selecionado = col_a.number_input(
        "Ano",
        min_value=2020,
        max_value=2100,
        value=ano_atual,
        key="select_ano",
    )

    # Formatação do filtro de busca YYYY-MM
    filtro_mes = f"{ano_selecionado:04d}-{mes_num:02d}"

    query_mes = """
    SELECT t.data, b.nome AS banco, t.tipo, t.valor, t.descricao
    FROM transacoes t
    JOIN bancos b ON t.banco_id = b.id
    WHERE strftime('%Y-%m', t.data) = ?
    ORDER BY t.data DESC
    """
    df_mes = pd.read_sql_query(query_mes, conn, params=(filtro_mes,))

    if not df_mes.empty:
        total_debito_mes = df_mes[df_mes["tipo"] == "Débito"]["valor"].sum()
        total_credito_mes = df_mes[df_mes["tipo"] == "Crédito"]["valor"].sum()
        total_geral_mes = total_debito_mes + total_credito_mes

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Débito no Mês", f"R$ {total_debito_mes:.2f}")
        c2.metric("Total Crédito no Mês", f"R$ {total_credito_mes:.2f}")
        c3.metric("Total Acumulado", f"R$ {total_geral_mes:.2f}")

        st.markdown("#### Detalhamento por Banco no Mês")
        resumo_banco = (
            df_mes.groupby(["banco", "tipo"])["valor"].sum().unstack(fill_value=0)
        )

        for col in ["Débito", "Crédito"]:
            if col not in resumo_banco.columns:
                resumo_banco[col] = 0.0

        resumo_banco["Total"] = resumo_banco["Débito"] + resumo_banco["Crédito"]
        st.dataframe(
            resumo_banco[["Débito", "Crédito", "Total"]].style.format(
                "R$ {:.2f}"
            ),
            use_container_width=True,
        )

        st.markdown("#### Histórico do Mês")
        st.dataframe(
            df_mes[["data", "banco", "tipo", "valor", "descricao"]],
            use_container_width=True,
        )
    else:
        st.info(f"Nenhum lançamento encontrado para {mes_nome} de {ano_selecionado}.")