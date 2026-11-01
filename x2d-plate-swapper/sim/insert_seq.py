import math, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyArrowPatch
plt.rcParams["font.family"]="IPAGothic"
ZB=93; L=272; PIN_X=45+L; TH=12
def plate(ax, rear_x, th, c, lab):
    t=math.radians(th); fx=rear_x-L*math.cos(t); fz=ZB+L*math.sin(t)
    ax.plot([rear_x,fx],[ZB,fz],color=c,lw=3,label=lab)
    ax.add_patch(Circle((fx,fz),6,fc="#8e44ad",ec="k",zorder=5))
    return fx,fz
fig,axs=plt.subplots(1,3,figsize=(16,4.6),sharey=True)
steps=[(-10,TH,"① 受け台の上で手前だけ持ち上げる（約12°）\n奥の端は受け台に乗ったまま"),
       (PIN_X-3,TH,"② 斜めのまま奥へ押し込む\n奥の端がベッド上を滑り、ピンに当たって止まる"),
       (PIN_X,0,"③ 奥のピンを支点に手前を弧を描いて下ろす\nフックは前後に±3mm遊ばせて追従")]
for ax,(rx,th,title) in zip(axs,steps):
    ax.add_patch(Rectangle((0,0),406,ZB,fc="#bdc3c7",alpha=.5)); ax.text(200,40,"X2D ベッド",ha="center")
    ax.add_patch(Rectangle((-300,ZB-12),300,12,fc="#27ae60",alpha=.3)); ax.text(-150,ZB-35,"受け台",ha="center",color="#1e8449")
    ax.axvline(0,color="#e67e22",ls="--"); ax.text(3,ZB+150,"ドア面",color="#d35400",fontsize=9)
    ax.add_patch(Rectangle((PIN_X,ZB),5,10,color="k")); ax.text(PIN_X-20,ZB+16,"奥ピン",fontsize=9)
    if th==0:
        for a in (12,8,4):
            plate(ax,rx,a,"#bbb","")
    fx,fz=plate(ax,rx,th,"#2c3e50","")
    ax.annotate("フック(T字ピン)",(fx,fz),(fx-90,fz+60),arrowprops=dict(arrowstyle="->"),fontsize=9)
    ax.set_title(title,fontsize=11); ax.set_xlim(-320,420); ax.set_ylim(0,260); ax.set_aspect("equal"); ax.grid(alpha=.2)
    ax.set_xlabel("x mm（＋が奥）")
axs[0].set_ylabel("z mm")
axs[1].annotate("",(PIN_X-3-L*math.cos(math.radians(TH)),ZB+L*math.sin(math.radians(TH))+25),(-10-L*math.cos(math.radians(TH)),ZB+L*math.sin(math.radians(TH))+25),arrowprops=dict(arrowstyle="->",color="#16a085",lw=2))
fig.text(.01,.01,"フック高さ：ベッド面＋約57mm（12°時） / 弧を下ろす間のフック前後移動は約6mm / 寸法は仮定値",fontsize=9,color="#555")
plt.tight_layout(rect=(0,.04,1,1)); plt.savefig("x2d_insert_sequence.png",dpi=110)
print("dz=%.0f dx=%.1f"%(L*math.sin(math.radians(TH)),L*(1-math.cos(math.radians(TH)))))
