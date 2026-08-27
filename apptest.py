import os
import sqlite3
from datetime import date, datetime
import extra_streamlit_components as stx
from github import Github
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Controle de Gastos Leve", page_icon="💳")

# --- INTEGRAÇÃO COM GITHUB (PERSISTÊNCIA DE DADOS) ---
DB_FILE = "gastos.db"


@st.cache_resource
def get_github_repo():
  try:
    g = Github(st.secrets["GITHUB_TOKEN"])
    return g.get_repo(st.secrets["REPO_NAME"])
  except Exception as e:
    st.error(f"Erro ao conectar com o GitHub: {e}")
    return None


def baixar_banco_github():
  repo = get_github_repo()
  if repo and "db_baixado" not in st.session_state:
    try:
      content = repo.get_contents(DB_FILE)
      with open(DB_FILE, "wb") as f:
        f.write(content.decoded_content)
      st.session_state["db_baixado"] = True
    except Exception:
      pass


def salvar_banco_github(
    mensagem_commit="Atualizando gastos.db via Streamlit",
):
  repo = get_github_repo()
  if not repo:
    return

  if os.path.exists(DB_FILE):
    with open(DB_FILE, "rb") as f:
      conteudo_bytes = f.read()

    try:
      file_bytes = repo.get_contents(DB_FILE)
      repo.update_file(
          path=DB_FILE,
          message=mensagem_commit,
          content=conteudo_bytes,
          sha=file_bytes.sha,
      )
    except Exception:
      repo.create_file(
          path=DB_FILE, message=mensagem_commit, content=conteudo_bytes
      )


baixar_banco_github()

# --- CONFIGURAÇÃO DE SEGURANÇA E COOKIE ---
SENHA_CORRETA = "suasenha123"


def get_cookie_manager():
  return stx.CookieManager()


cookie_manager = get_cookie_manager()

# --- CONEXÃO E CRIAÇÃO DO BANCO DE DADOS ---
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
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


# --- SISTEMA DE LOGIN COM PERSISTÊNCIA ---
def autenticar():
  auth_cookie = cookie_manager.get(cookie="auth_gastos_app")

  if "autenticado" not in st.session_state:
    if auth_cookie == "autenticado_ok":
      st.session_state["autenticado"] = True
    else:
      st.session_state["autenticado"] = False

  if not st.session_state["autenticado"]:
    st.title("🔒 Acesso Restrito")
    senha_input = st.text_input(
        "Digite a senha para acessar:", type="password"
    )
    if st.button("Entrar"):
      if senha_input == SENHA_CORRETA:
        st.session_state["autenticado"] = True
        cookie_manager.set(
            "auth_gastos_app",
            "autenticado_ok",
            expires_at=datetime(2030, 1, 1),
        )
        st.success("Login efetuado! Recarregando...")
        st.rerun()
      else:
        st.error("Senha incorreta!")
    return False
  return True


if not autenticar():
  st.stop()

# --- APLICAÇÃO PRINCIPAL ---
st.title("💳 Registro Rápido de Gastos")

aba1, aba2, aba3, aba4 = st.tabs([
    "📝 Registrar Gasto",
    "📅 Resumo Mensal",
    "🗑️ Gerenciar/Apagar Gastos",
    "🏦 Bancos",
])

# --- ABA: GERENCIAR BANCOS ---
with aba4:
  st.subheader("Cadastrar Novo Banco/Cartão")
  novo_banco = st.text_input("Nome do Banco ou Cartão").strip()
  if st.button("Adicionar Banco"):
    if novo_banco:
      try:
        cursor.execute("INSERT INTO bancos (nome) VALUES (?)", (novo_banco,))
        conn.commit()
        salvar_banco_github(f"Adicionado banco: {novo_banco}")
        st.success(f"Banco '{novo_banco}' adicionado com sucesso!")
        st.rerun()
      except sqlite3.IntegrityError:
        st.warning("Este banco já está cadastrado.")
    else:
      st.error("Informe um nome válido.")

  st.divider()

  st.subheader("🗑️ Excluir Banco/Cartão")
  bancos_df_excluir = pd.read_sql_query(
      "SELECT id, nome FROM bancos ORDER BY nome", conn
  )

  if not bancos_df_excluir.empty:
    banco_excluir_nome = st.selectbox(
        "Selecione o banco que deseja remover:",
        options=bancos_df_excluir["nome"].tolist(),
        key="select_banco_excluir",
    )

    if st.button("❌ Remover Banco Selecionado", type="primary"):
      banco_id_excluir = int(
          bancos_df_excluir[bancos_df_excluir["nome"] == banco_excluir_nome][
              "id"
          ].values[0]
      )

      cursor.execute(
          "SELECT COUNT(*) FROM transacoes WHERE banco_id = ?",
          (banco_id_excluir,),
      )
      qtd_transacoes = cursor.fetchone()[0]

      if qtd_transacoes > 0:
        st.error(
            f"Não é possível apagar o banco '{banco_excluir_nome}' pois existem"
            f" {qtd_transacoes} gasto(s) vinculados a ele. Apague os gastos"
            " primeiro!"
        )
      else:
        cursor.execute("DELETE FROM bancos WHERE id = ?", (banco_id_excluir,))
        conn.commit()
        salvar_banco_github(f"Banco removido: {banco_excluir_nome}")
        st.success(f"Banco '{banco_excluir_nome}' removido com sucesso!")
        st.rerun()
  else:
    st.info("Nenhum banco cadastrado no momento.")

bancos_df = pd.read_sql_query("SELECT id, nome FROM bancos", conn)

# --- ABA: REGISTRAR GASTO ---
with aba1:
  if bancos_df.empty:
    st.info(
        "Nenhum banco cadastrado ainda. Vá na aba 'Bancos' para adicionar o"
        " primeiro."
    )
  else:
    st.subheader("Novo Lançamento")
    with st.form("form_transacao", clear_on_submit=True):
      col1, col2 = st.columns(2)
      with col1:
        banco_selecionado = st.selectbox(
            "Selecione o Banco", options=bancos_df["nome"].tolist()
        )
        tipo = st.radio(
            "Tipo de Pagamento", ["Débito", "Crédito"], horizontal=True
        )
      with col2:
        valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        data_gasto = st.date_input("Data", value=date.today())

      descricao = st.text_input("Descrição (Opcional)")
      submitted = st.form_submit_button("Registrar Gasto")

      if submitted:
        banco_id = int(
            bancos_df[bancos_df["nome"] == banco_selecionado]["id"].values[0]
        )
        cursor.execute(
            "INSERT INTO transacoes (data, banco_id, tipo, valor, descricao)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                data_gasto.strftime("%Y-%m-%d"),
                banco_id,
                tipo,
                valor,
                descricao,
            ),
        )
        conn.commit()
        salvar_banco_github(
            f"Novo gasto registrado: R$ {valor:.2f} em {banco_selecionado}"
        )
        st.success("Gasto registrado e salvo com sucesso!")

  st.divider()
  st.subheader("📊 Resumo do Dia")
  data_filtro = st.date_input("Filtrar por data", value=date.today())

  query_dia = """
    SELECT t.id, t.data, b.nome AS banco, t.tipo, t.valor, t.descricao
    FROM transacoes t
    JOIN bancos b ON t.banco_id = b.id
    WHERE t.data = ?
    ORDER BY t.id DESC
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

    # BOTÕES DE EXPORTAÇÃO (CSV E XML)
    c_csv, c_xml = st.columns(2)

    csv_dia = df_dia.to_csv(index=False, sep=";", decimal=",").encode(
        "utf-8-sig"
    )
    c_csv.download_button(
        label="📥 Exportar CSV (Excel)",
        data=csv_dia,
        file_name=f"gastos_{data_filtro.strftime('%Y_%m_%d')}.csv",
        mime="text/csv",
    )

    xml_dia = df_dia.to_xml(index=False, root_name="gastos", row_name="gasto")
    c_xml.download_button(
        label="📄 Exportar XML",
        data=xml_dia,
        file_name=f"gastos_{data_filtro.strftime('%Y_%m_%d')}.xml",
        mime="application/xml",
    )
  else:
    st.info("Nenhum registro encontrado para esta data.")

# --- ABA: RESUMO MENSAL ---
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

  filtro_mes = f"{ano_selecionado:04d}-{mes_num:02d}"

  query_mes = """
    SELECT t.id, t.data, b.nome AS banco, t.tipo, t.valor, t.descricao
    FROM transacoes t
    JOIN bancos b ON t.banco_id = b.id
    WHERE strftime('%Y-%m', t.data) = ?
    ORDER BY t.data DESC
    """
  df_mes = pd.read_sql_query(query_mes, conn, params=(filtro_mes,))

  total_debito_mes = (
      df_mes[df_mes["tipo"] == "Débito"]["valor"].sum()
      if not df_mes.empty
      else 0.0
  )
  total_credito_mes = (
      df_mes[df_mes["tipo"] == "Crédito"]["valor"].sum()
      if not df_mes.empty
      else 0.0
  )
  total_geral_mes = total_debito_mes + total_credito_mes

  c1, c2, c3 = st.columns(3)
  c1.metric("Total Débito no Mês", f"R$ {total_debito_mes:.2f}")
  c2.metric("Total Crédito no Mês", f"R$ {total_credito_mes:.2f}")
  c3.metric("Total Acumulado", f"R$ {total_geral_mes:.2f}")

  st.markdown("---")

  # --- NOVO RECURSO: SIMULAÇÃO / GRÁFICO DE SALDOS E LIMITES ---
  st.subheader("💰 Visão de Patrimônio e Limites")

  col_lim1, col_lim2 = st.columns(2)
  saldo_conta = col_lim1.number_input(
      "Dinheiro Atual na Conta (R$)", min_value=0.0, value=1000.0, step=100.0
  )
  limite_total = col_lim2.number_input(
      "Limite Total do Cartão de Crédito (R$)",
      min_value=0.0,
      value=3000.0,
      step=100.0,
  )

  limite_restante = max(0.0, limite_total - total_credito_mes)

  # Dados para o gráfico com fatias separadas
  labels_pat = [
      "Dinheiro em Conta",
      "Limite de Crédito Utilizado",
      "Limite Livre Restante",
  ]
  valores_pat = [saldo_conta, total_credito_mes, limite_restante]

  # Criando gráfico com fatias separadas (pull) e valor + porcentagem no texto
  fig_patrimonio = go.Figure(
      data=[
          go.Pie(
              labels=labels_pat,
              values=valores_pat,
              pull=[
                  0.05,
                  0.05,
                  0.05,
              ],  # Afasta levemente cada fatia da outra
              textinfo="value+percent",  # Exibe o R$ e a % na fatia
              texttemplate="R$ %{value:.2f}<br>(%{percent})",
              hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:.2f}<br>Porcentagem: %{percent}<extra></extra>",
              marker=dict(colors=["#2ecc71", "#e74c3c", "#3498db"]),
          )
      ]
  )
  fig_patrimonio.update_layout(
      title_text="Distribuição de Caixa vs Limite de Crédito", height=400
  )
  st.plotly_chart(fig_patrimonio, use_container_width=True)

  st.markdown("---")

  if not df_mes.empty:
    st.subheader("📈 Análise Gráfica dos Gastos")

    col_g1, col_g2 = st.columns(2)

    with col_g1:
      df_graf_banco = (
          df_mes.groupby(["banco", "tipo"])["valor"].sum().reset_index()
      )
      fig_bar = px.bar(
          df_graf_banco,
          x="banco",
          y="valor",
          color="tipo",
          barmode="group",
          title="Gastos por Banco (Débito vs Crédito)",
          labels={"valor": "Valor (R$)", "banco": "Banco", "tipo": "Tipo"},
          text_auto=".2f",
      )
      fig_bar.update_layout(xaxis_title="", yaxis_title="R$")
      st.plotly_chart(fig_bar, use_container_width=True)

    with col_g2:
      df_graf_pizza = df_mes.groupby("banco")["valor"].sum().reset_index()
      fig_pie = px.pie(
          df_graf_pizza,
          values="valor",
          names="banco",
          title="Participação de Cada Banco no Mês",
          hole=0.3,
      )
      fig_pie.update_traces(
          textinfo="value+percent", texttemplate="R$ %{value:.2f}<br>(%{percent})"
      )
      st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Detalhamento por Banco no Mês")
    resumo_banco = (
        df_mes.groupby(["banco", "tipo"])["valor"].sum().unstack(fill_value=0)
    )

    for col in ["Débito", "Crédito"]:
      if col not in resumo_banco.columns:
        resumo_banco[col] = 0.0

    resumo_banco["Total"] = resumo_banco["Débito"] + resumo_banco["Crédito"]
    st.dataframe(
        resumo_banco[["Débito", "Crédito", "Total"]].style.format("R$ {:.2f}"),
        use_container_width=True,
    )

    st.markdown("#### Histórico do Mês")
    st.dataframe(
        df_mes[["data", "banco", "tipo", "valor", "descricao"]],
        use_container_width=True,
    )

    # BOTÕES DE EXPORTAÇÃO DO MÊS (CSV E XML)
    c_csv_m, c_xml_m = st.columns(2)

    csv_mes = df_mes.to_csv(index=False, sep=";", decimal=",").encode(
        "utf-8-sig"
    )
    c_csv_m.download_button(
        label=f"📥 Exportar {mes_nome} (CSV)",
        data=csv_mes,
        file_name=f"gastos_{ano_selecionado}_{mes_num:02d}.csv",
        mime="text/csv",
    )

    xml_mes = df_mes.to_xml(index=False, root_name="gastos", row_name="gasto")
    c_xml_m.download_button(
        label=f"📄 Exportar {mes_nome} (XML)",
        data=xml_mes,
        file_name=f"gastos_{ano_selecionado}_{mes_num:02d}.xml",
        mime="application/xml",
    )
  else:
    st.info(
        f"Nenhum lançamento encontrado para {mes_nome} de {ano_selecionado}."
    )

# --- ABA: GERENCIAR E APAGAR GASTOS ---
with aba3:
  st.subheader("🗑️ Apagar Registro de Gasto")

  query_todos = """
    SELECT t.id, t.data, b.nome AS banco, t.tipo, t.valor, t.descricao
    FROM transacoes t
    JOIN bancos b ON t.banco_id = b.id
    ORDER BY t.data DESC, t.id DESC
    LIMIT 50
    """
  df_todos = pd.read_sql_query(query_todos, conn)

  if not df_todos.empty:
    st.write("Selecione um lançamento recente para apagar:")

    opcoes = {
        row[
            "id"
        ]: f"ID {row['id']} | {row['data']} | {row['banco']} | {row['tipo']} | R$ {row['valor']:.2f} ({row['descricao']})"
        for _, row in df_todos.iterrows()
    }

    gasto_id_selecionado = st.selectbox(
        "Selecione o registro:",
        options=list(opcoes.keys()),
        format_func=lambda x: opcoes[x],
    )

    if st.button("❌ Apagar Gasto Selecionado", type="primary"):
      cursor.execute(
          "DELETE FROM transacoes WHERE id = ?", (gasto_id_selecionado,)
      )
      conn.commit()
      salvar_banco_github(f"Gasto ID {gasto_id_selecionado} removido")
      st.success("Gasto removido e alterações salvas no GitHub!")
      st.rerun()
  else:
    st.info("Nenhum gasto cadastrado para apagar.")
