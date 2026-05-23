import os
import pandas as pd
from flask import Flask, render_template, request, redirect, session, flash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static'),
)
app.secret_key = "ecommerce_key"

@app.route('/')
def login_page():
    session.clear()
    return render_template('login.html')

@app.route('/auth', methods=['POST'])
def auth():
    if request.form.get('username') == 'admin' and request.form.get('password') == '1234':
        session['user'] = 'admin'
        return redirect('/dashboard')
    flash("Invalid credentials!", "danger")
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')

    # Original table
    raw_cols, raw_data, violation_rows = [], [], []
    raw_path = os.path.join(BASE_DIR, 'uploaded_data.csv')
    if os.path.exists(raw_path):
        df = pd.read_csv(raw_path)
        raw_cols = df.columns.tolist()
        raw_data = df.values.tolist()

        # Highlight violation rows: find rows where same determinant has multiple values of attr1 OR attr2
        d = session.get('decomp')
        if d:
            det, attr1, attr2 = d['det'], d['attr1'], d['attr2']
            if det in df.columns and attr1 in df.columns and attr2 in df.columns:
                # A row is a violation if its determinant value maps to >1 unique attr1 OR >1 unique attr2
                mvd1 = df.groupby(det)[attr1].nunique()
                mvd2 = df.groupby(det)[attr2].nunique()
                violation_dets = set(
                    list(mvd1[mvd1 > 1].index) + list(mvd2[mvd2 > 1].index)
                )
                violation_rows = [
                    i for i, row in enumerate(df[det].tolist())
                    if row in violation_dets
                ]

    # Decomposed tables
    t1_data, t2_data, t1_cols, t2_cols = [], [], [], []
    d = session.get('decomp')
    if d:
        p1 = os.path.join(BASE_DIR, f"table_{d['attr1']}.csv")
        p2 = os.path.join(BASE_DIR, f"table_{d['attr2']}.csv")
        if os.path.exists(p1):
            df1 = pd.read_csv(p1)
            t1_cols = df1.columns.tolist()
            t1_data = df1.values.tolist()
        if os.path.exists(p2):
            df2 = pd.read_csv(p2)
            t2_cols = df2.columns.tolist()
            t2_data = df2.values.tolist()

    return render_template('dashboard.html',
        raw_cols=raw_cols, raw_data=raw_data, violation_rows=violation_rows,
        t1_cols=t1_cols, t1_data=t1_data,
        t2_cols=t2_cols, t2_data=t2_data,
        decomp=d
    )

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session: return redirect('/')
    file = request.files.get('file')
    if not file or file.filename == '':
        flash("No file selected!", "danger")
        return redirect('/dashboard')
    try:
        df = pd.read_csv(file)
        session['columns'] = df.columns.tolist()
        session['rows'] = len(df)
        session.pop('decomp', None)
        df.to_csv(os.path.join(BASE_DIR, 'uploaded_data.csv'), index=False)
        flash(f"✅ Uploaded {len(df)} rows | Columns: {', '.join(df.columns)}", "success")
    except Exception as e:
        flash(f"Upload failed: {e}", "danger")
    return redirect('/dashboard')

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return redirect('/')
    path = os.path.join(BASE_DIR, 'uploaded_data.csv')
    if not os.path.exists(path):
        flash("No dataset found. Upload a CSV first.", "warning")
        return redirect('/dashboard')
    try:
        df = pd.read_csv(path)
        fds, mvds = [], []
        cols = df.columns.tolist()
        for det in cols:
            for dep in cols:
                if det == dep: continue
                if (df.groupby(det)[dep].nunique() == 1).all():
                    fds.append(f"{det} → {dep}")
        for det in cols:
            others = [c for c in cols if c != det]
            for dep in others:
                rest = [c for c in others if c != dep]
                if not rest: continue
                for _, grp in df.groupby(det):
                    if grp[dep].nunique() > 1 and grp[rest].drop_duplicates().shape[0] > 1:
                        mvds.append(f"{det} →→ {dep}")
                        break
        session['fds']  = fds
        session['mvds'] = list(set(mvds))
        flash(f"🔍 FDs: {' | '.join(fds) or 'None'}  ||  MVDs: {' | '.join(set(mvds)) or 'None'}", "info")
    except Exception as e:
        flash(f"Analysis failed: {e}", "danger")
    return redirect('/dashboard')

@app.route('/run-4nf', methods=['POST'])
def run_4nf():
    if 'user' not in session: return redirect('/')
    det   = request.form.get('determinant', '').strip()
    attr1 = request.form.get('attr1', '').strip()
    attr2 = request.form.get('attr2', '').strip()
    path  = os.path.join(BASE_DIR, 'uploaded_data.csv')
    if not os.path.exists(path):
        flash("No dataset found. Upload a CSV first.", "warning")
        return redirect('/dashboard')
    try:
        df = pd.read_csv(path)
        for col in [det, attr1, attr2]:
            if col not in df.columns:
                flash(f"Column '{col}' not found. Available: {', '.join(df.columns)}", "danger")
                return redirect('/dashboard')
        t1 = df[[det, attr1]].drop_duplicates().reset_index(drop=True)
        t2 = df[[det, attr2]].drop_duplicates().reset_index(drop=True)
        t1.to_csv(os.path.join(BASE_DIR, f'table_{attr1}.csv'), index=False)
        t2.to_csv(os.path.join(BASE_DIR, f'table_{attr2}.csv'), index=False)
        session['decomp'] = {'det': det, 'attr1': attr1, 'attr2': attr2,
                             't1_rows': len(t1), 't2_rows': len(t2)}
        flash(f"✅ 4NF complete! table_{attr1} ({len(t1)} rows) & table_{attr2} ({len(t2)} rows)", "success")
    except Exception as e:
        flash(f"Decomposition failed: {e}", "danger")
    return redirect('/dashboard')

@app.route('/download/<filename>')
def download(filename):
    if 'user' not in session: return redirect('/')
    from flask import send_file
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    flash("File not found.", "danger")
    return redirect('/dashboard')

if __name__ == '__main__':
    app.run(debug=True)