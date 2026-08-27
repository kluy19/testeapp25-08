import os
import sqlite3
from datetime import date, datetime
import extra_streamlit_components as stx
from github import Github
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Controle de Gastos Leve", page_icon="💳")

# --- INTEGRAÇÃO COM GITHUB (PERSISTÊNCIA DE DADOS) ---
DB_FILE = "gastos.db"


@st.cache_resource
def get_github_repo():
  """Conecta à API do GitHub usando as credenciais salvas nos Secrets."""
  try:
    g = Github(st.secrets["GITHUB_TOKEN"])
    return g.get_repo(st.secrets["REPO_NAME"])
  except Exception as e:
    st.error(f"Erro ao conectar com o GitHub: {e}")
    return None


def baixar_banco_github():
  """Garante que o banco de dados mais recente do GitHub esteja salvo localmente ao iniciar."""
  repo = get_github_repo()
  if repo and "db_baixado" not in st.session_state:
    try:
      content = repo.get_contents(DB_FILE)
      with open(DB_FILE, "wb") as f:
        f.write(content.decoded_content)
      st.session_state["db_baixado"] = True
    except Exception:
      # Se o arquivo ainda não existir no GitHub, ele será criado no primeiro commit
      pass


def salvar_banco_github(
    mensagem_commit="Atualizando gastos.db via Streamlit",
):
  """Envia a versão atualizada do gastos.db para o repositório no GitHub."""
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


# Baixar a versão mais atual do banco ao carregar o app
baixar_banco_github()

# --- CONFIGURAÇÃO DE SEGURANÇA E COOKIE ---
SENHA_CORRETA = "suasenha123"  # Mude para a sua senha desejada


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

    # Exportar gastos do dia
    csv_dia = df_dia.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Exportar Gastos do Dia (CSV)",
        data=csv_dia,
        file_name=f"gastos_{data_filtro.strftime('%Y_%m_%d')}.csv",
        mime="text/csv",
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
        resumo_banco[["Débito", "Crédito", "Total"]].style.format("R$ {:.2f}"),
        use_container_width=True,
    )

    st.markdown("#### Histórico do Mês")
    st.dataframe(
        df_mes[["data", "banco", "tipo", "valor", "descricao"]],
        use_container_width=True,
    )

    # Exportar gastos do mês
    csv_mes = df_mes.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"📥 Exportar Gastos de {mes_nome} (CSV)",
        data=csv_mes,
        file_name=f"gastos_{ano_selecionado}_{mes_num:02d}.csv",
        mime="text/csv",
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
