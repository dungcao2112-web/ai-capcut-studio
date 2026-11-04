/* Văn Phòng 3D — MocapGait: bộ tổng hợp dáng đi đa hài chuẩn mocap người thật (CMU / Mixamo walk cycles).
 * Mọi góc tính bằng radian trong KHÔNG GIAN ROOT của model (mặt hướng +Z, +X = bên TRÁI nhân vật, +Y = lên):
 *   x = gập/duỗi (pitch: -x đưa chi ra trước), y = xoay trục (yaw), z = nghiêng/khép-dạng (roll: +z nâng phía +X).
 *   f = gập khớp bản lề (gối gập ra sau / khuỷu gập ra trước) theo trục tính sẵn từ rest pose của từng rig.
 *   px/py/pz = dịch chuyển chậu (mét người thật, controller tự quy đổi theo chiều cao hông của model).
 * Pha chu kỳ p ∈ [0,1) tính theo CHÂN TRÁI: p = 0 chạm gót trái, ~0.62 rời mũi trái, chân phải lệch 0.5 chu kỳ. */
(function () {
  'use strict';
  const TAU = Math.PI * 2;
  const wrap = (d) => d - Math.round(d);
  // Bump Gauss tuần hoàn: đỉnh tại c (pha), độ rộng w (pha)
  const bump = (p, c, w) => { const d = wrap(p - c); return Math.exp(-(d * d) / (2 * w * w)); };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  // --- Chân (p = pha riêng của chân đó, side = +1 trái / -1 phải)
  function leg(p, side, amp) {
    const hip = amp * (0.08 + 0.40 * Math.cos(TAU * (p - 0.92)));          // +0.48 trước (cuối pha vung) / -0.32 sau (rời mũi)
    const knee = 0.06 + 0.18 * bump(p, 0.12, 0.055)                         // đỉnh 1: giảm chấn sau chạm gót (~0.24 rad)
      + (0.70 + 0.32 * amp) * bump(p, 0.72, 0.105);                         // đỉnh 2: lăng chân (~1.08 rad ≈ 62°)
    const ankle = 0.18 * bump(p, 0.0, 0.045)                                // chạm gót ngửa mũi
      + 0.10 * bump(p, 0.42, 0.11)                                          // cẳng chân lướt qua bàn chân
      - 0.36 * bump(p, 0.62, 0.055)                                         // đạp mũi rời đất
      + 0.12 * bump(p, 0.84, 0.08);                                         // nhấc mũi qua sàn ở pha vung
    return {
      thigh: { x: -hip - 0.04, z: -side * 0.035 * bump(p, 0.30, 0.16) },    // khép nhẹ (adduction) ở pha trụ
      shin: { f: knee },
      foot: { x: -ankle },
      toe: { x: -0.45 * bump(p, 0.60, 0.06) }                               // gập ngón lúc đạp mũi
    };
  }

  // --- Tay: con lắc bất đối xứng, đối pha chân cùng bên
  function arm(pLeg, side, amp, out, sfx) {
    const c = Math.cos(TAU * (pLeg - 0.92));
    const a = amp * (0.38 * -c - 0.04);                                     // +0.34 ra trước / -0.42 ra sau
    out['shoulder' + sfx] = { x: -0.05 * a, z: side * 0.012 * Math.abs(a) };
    out['upperArm' + sfx] = { x: -a, z: -side * 0.08 * Math.max(0, a) };     // đánh ra trước hơi khép vào trong
    out['forearm' + sfx] = { f: 0.48 - 0.20 * Math.cos(TAU * (pLeg - 0.92) - 0.35) }; // 0.28..0.68 rad, trễ pha 0.35
    out['hand' + sfx] = { x: -0.06 * -c, z: side * 0.05 };
  }

  // Dáng đi: p = pha chân trái, ctx = { amp, lean, bank, look }
  function walk(p, ctx) {
    const amp = ctx.amp, cL = Math.cos(TAU * (p - 0.92)), list = Math.sin(TAU * (p + 0.05));
    const o = {
      hips: {
        x: 0.04 * ctx.lean, y: -0.085 * amp * cL, z: 0.065 * amp * list,  // nghiêng trước / xoay chậu / pelvic list
        px: 0.024 * amp * Math.sin(TAU * p),                                // dồn trọng tâm sang chân trụ
        py: -0.011 * (1 - Math.cos(2 * TAU * (p - 0.25)))                   // nhún 2 nhịp/chu kỳ (cao nhất giữa pha trụ)
      },
      spine: { x: 0.03 * ctx.lean, y: 0.07 * amp * cL, z: ctx.bank * 0.6 },
      chest: { x: 0.02 * ctx.lean, y: 0.07 * amp * cL, z: -0.045 * amp * list + ctx.bank * 0.4 }, // ngực & vai đối pha chậu
      neck: { y: -0.025 * amp * cL, x: -0.02 * ctx.lean },
      head: { y: -0.03 * amp * cL + ctx.look, x: -0.03 * ctx.lean + 0.012 * Math.cos(2 * TAU * p), z: -ctx.bank * 0.5 }
    };
    const L = leg(p, 1, amp), R = leg((p + 0.5) % 1, -1, amp);
    o.thighL = L.thigh; o.shinL = L.shin; o.footL = L.foot; o.toeL = L.toe;
    o.thighR = R.thigh; o.shinR = R.shin; o.footR = R.foot; o.toeR = R.toe;
    arm(p, 1, amp, o, 'L'); arm((p + 0.5) % 1, -1, amp, o, 'R');
    return o;
  }

  // Đứng tự nhiên: thở, đổi trụ chân chu kỳ ~6.2s, nhìn quanh
  function stand(t, ctx) {
    const ws = Math.sin(TAU * t / 6.2), br = Math.sin(TAU * t / 4.2);
    const relaxL = Math.max(0, -ws), relaxR = Math.max(0, ws);
    const look = 0.22 * Math.sin(t * 0.31) * Math.sin(t * 0.17 + 1.0) + (ctx.look || 0);
    return {
      hips: { px: 0.016 * ws, z: 0.03 * ws, y: 0.03 * ws, py: -0.006 * Math.abs(ws) },
      spine: { x: 0.01 + 0.006 * br, z: -0.012 * ws },
      chest: { x: -0.012 * br, z: -0.015 * ws },
      neck: { y: look * 0.4 },
      head: { y: look * 0.6, x: 0.03 * Math.sin(t * 0.23), z: 0.02 * Math.sin(t * 0.41) },
      thighL: { x: -0.06 * relaxL, z: -0.03 * ws }, shinL: { f: 0.04 + 0.14 * relaxL }, footL: { x: 0.05 * relaxL },
      thighR: { x: -0.06 * relaxR, z: -0.03 * ws }, shinR: { f: 0.04 + 0.14 * relaxR }, footR: { x: 0.05 * relaxR },
      shoulderL: { z: 0.008 * br }, shoulderR: { z: -0.008 * br },
      upperArmL: { x: 0.02 * Math.sin(t * 0.7), z: 0.01 * br }, upperArmR: { x: 0.02 * Math.sin(t * 0.7 + 1), z: -0.01 * br },
      forearmL: { f: 0.2 }, forearmR: { f: 0.2 },
      handL: { z: 0.05 }, handR: { z: -0.05 }
    };
  }

  // Lớp cộng thêm cho tư thế ngồi / chơi (clip giữ tư thế, lớp này thêm sự sống)
  function overlay(kind, t, ctx) {
    const br = Math.sin(TAU * t / 4.0);
    const o = { chest: { x: -0.014 * br }, spine: { x: 0.006 * br }, head: { y: ctx.look || 0 } };
    if (kind === 'sit_work' || kind === 'sit_desk') {
      const burst = clamp(Math.sin(t * 0.7) * 3, 0, 1);                     // gõ phím theo từng đợt
      o.handL = { x: 0.07 * burst * Math.sin(t * 37) };
      o.handR = { x: 0.07 * burst * Math.sin(t * 41 + 1.3) };
      o.forearmL = { f: 0.03 * burst * Math.sin(t * 23) };
      o.forearmR = { f: 0.03 * burst * Math.sin(t * 29 + 0.7) };
      o.head.y += 0.06 * Math.sin(t * 0.4); o.head.x = 0.02 * Math.sin(t * 0.9);
    } else if (/^sit/.test(kind)) {
      const sip = bump((t / 11) % 1, 0.5, 0.06);                            // nhấp trà mỗi ~11s
      o.head.z = 0.07 * Math.sin(t * 0.25); o.head.y += 0.1 * Math.sin(t * 0.18); o.head.x = 0.08 * sip;
      o.upperArmR = { x: -0.25 * sip }; o.forearmR = { f: 0.5 * sip };
    } else if (kind === 'play') {
      o.head.z = 0.06 * Math.sin(t * 2.6); o.hips = { py: 0.01 * Math.abs(Math.sin(t * 4.5)) };
    }
    return o;
  }

  // Trộn tuyến tính 2 bộ góc (walk ↔ stand) theo trọng số w của walk
  function blend(a, b, w) {
    const out = {};
    new Set(Object.keys(a).concat(Object.keys(b))).forEach((k) => {
      const x = a[k] || {}, y = b[k] || {}, o = {};
      new Set(Object.keys(x).concat(Object.keys(y))).forEach((c) => { o[c] = (x[c] || 0) * w + (y[c] || 0) * (1 - w); });
      out[k] = o;
    });
    return out;
  }

  window.MocapGait = { walk, stand, overlay, blend, bump };
})();
