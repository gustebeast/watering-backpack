//! GLB loader for the cadkit.web exporter format. Materials are read as cadkit/web/trace_blender.py reads them.
use bytemuck::{Pod, Zeroable};
use serde_json::Value;
use std::collections::HashMap;

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub struct Vtx {
    pub n: [f32; 3],
    pub col: u32, // rgba8 linear, a=0 -> metal
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub struct GpuPart {
    pub idx_off: u32,
    pub vtx_off: u32,
    pub flags: u32, // FLAG_*
    pub pad: u32,
    pub color: [f32; 4],
    pub mr: [f32; 4], // metal, rough
}

pub const FLAG_VCOL: u32 = 1;
pub const FLAG_CLEAR: u32 = 2;
pub const FLAG_SEL: u32 = 4;

pub struct Part {
    pub name: String,
    pub idx_off: u32,
    pub idx_count: u32,
    pub vtx_off: u32,
    pub vtx_count: u32,
    pub clear: bool,
}

pub struct Scene {
    pub positions: Vec<[f32; 3]>,
    pub vattr: Vec<Vtx>,
    pub indices: Vec<u32>, // local to each part
    pub parts: Vec<Part>,
    pub gpu_parts: Vec<GpuPart>,
}

fn u32le(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes([b[o], b[o + 1], b[o + 2], b[o + 3]])
}

struct Acc<'a> {
    data: &'a [u8],
    count: usize,
    comp: u64,
    stride: usize,
}

fn accessor<'a>(j: &Value, bin: &'a [u8], idx: u64, elem_size: usize) -> Result<Acc<'a>, String> {
    let a = &j["accessors"][idx as usize];
    let bv = &j["bufferViews"][a["bufferView"].as_u64().ok_or("accessor without a bufferView")? as usize];
    let off = bv["byteOffset"].as_u64().unwrap_or(0) as usize + a["byteOffset"].as_u64().unwrap_or(0) as usize;
    let stride = bv["byteStride"].as_u64().map(|s| s as usize).unwrap_or(elem_size);
    if off > bin.len() {
        return Err("accessor outside the buffer".into());
    }
    Ok(Acc { data: &bin[off..], count: a["count"].as_u64().unwrap_or(0) as usize, comp: a["componentType"].as_u64().unwrap_or(0), stride })
}

pub fn load(d: &[u8]) -> Result<Scene, String> {
    if d.len() < 28 || &d[0..4] != b"glTF" {
        return Err("not a GLB".into());
    }
    let jl = u32le(d, 12) as usize;
    if 20 + jl + 8 > d.len() {
        return Err("truncated GLB".into());
    }
    let j: Value = serde_json::from_slice(&d[20..20 + jl]).map_err(|e| e.to_string())?;
    let bo = 20 + jl;
    let bl = u32le(d, bo) as usize;
    if bo + 8 + bl > d.len() {
        return Err("truncated GLB".into());
    }
    let bin = &d[bo + 8..bo + 8 + bl];

    // the model's own table: filament or finish -> (metalness, roughness[, room: not used here])
    let mut finishes: HashMap<String, (f32, f32)> = HashMap::new();
    if let Some(f) = j["asset"]["extras"]["finishes"].as_object() {
        for (k, v) in f {
            finishes.insert(k.clone(), (v[0].as_f64().unwrap_or(0.0) as f32, v[1].as_f64().unwrap_or(0.65) as f32));
        }
    }

    let mut s = Scene { positions: vec![], vattr: vec![], indices: vec![], parts: vec![], gpu_parts: vec![] };
    for node in j["nodes"].as_array().ok_or("no nodes")? {
        let Some(mi) = node["mesh"].as_u64() else { continue };
        let prim = &j["meshes"][mi as usize]["primitives"][0];
        let pa = accessor(&j, bin, prim["attributes"]["POSITION"].as_u64().ok_or("no POSITION")?, 12)?;
        let ia = accessor(&j, bin, prim["indices"].as_u64().ok_or("no indices")?, 0)?;
        let vtx_off = s.positions.len() as u32;
        let idx_off = s.indices.len() as u32;
        if pa.count == 0 || ia.count < 3 || pa.data.len() < (pa.count - 1) * pa.stride + 12 {
            continue;
        }
        for i in 0..pa.count {
            let o = i * pa.stride;
            s.positions.push(bytemuck::pod_read_unaligned(&pa.data[o..o + 12]));
        }
        match ia.comp {
            5121 => s.indices.extend(ia.data[..ia.count].iter().map(|&b| b as u32)),
            5123 => s.indices.extend((0..ia.count).map(|i| u16::from_le_bytes([ia.data[i * 2], ia.data[i * 2 + 1]]) as u32)),
            5125 => s.indices.extend((0..ia.count).map(|i| u32le(ia.data, i * 4))),
            c => return Err(format!("index component type {c}")),
        }
        // colours
        let mut cols = vec![0xffff_ffffu32; pa.count];
        let vcol = prim["attributes"]["COLOR_0"].as_u64();
        if let Some(ci) = vcol {
            let ca = accessor(&j, bin, ci, 4)?;
            for i in 0..pa.count.min(ca.count) {
                cols[i] = u32le(ca.data, i * ca.stride);
            }
        }
        // smooth normals: each face's, weighted by the angle it has at the vertex (as the reference tracer's)
        let pos = &s.positions[vtx_off as usize..];
        let mut nrm = vec![glam::Vec3::ZERO; pa.count];
        let idx = &s.indices[idx_off as usize..];
        for t in idx.chunks_exact(3) {
            let v = [glam::Vec3::from(pos[t[0] as usize]), glam::Vec3::from(pos[t[1] as usize]), glam::Vec3::from(pos[t[2] as usize])];
            let n = (v[1] - v[0]).cross(v[2] - v[0]).normalize_or_zero();
            for k in 0..3 {
                let (e1, e2) = ((v[(k + 1) % 3] - v[k]).normalize_or_zero(), (v[(k + 2) % 3] - v[k]).normalize_or_zero());
                nrm[t[k] as usize] += n * e1.dot(e2).clamp(-1.0, 1.0).acos();
            }
        }
        for i in 0..pa.count {
            let n = nrm[i].normalize_or(glam::Vec3::Z);
            s.vattr.push(Vtx { n: n.to_array(), col: cols[i] });
        }
        // material: a part of many colours carries them (and its metal, in alpha) per vertex under one
        // plain material; any other takes its colour from the file and its surface from the finishes table
        let mat = node["extras"]["mat"].as_str();
        let bc = &j["materials"][prim["material"].as_u64().unwrap_or(0) as usize]["pbrMetallicRoughness"]["baseColorFactor"];
        let mut color = if bc.is_array() { [0, 1, 2, 3].map(|k| bc[k].as_f64().unwrap_or(1.0) as f32) } else { [1.0; 4] };
        let (mut metal, mut rough) = mat.and_then(|m| finishes.get(m).copied()).unwrap_or((0.0, 0.65));
        let mut clear = mat.map(|m| m.ends_with("-clear")).unwrap_or(false);
        if vcol.is_some() {
            (color, metal, rough, clear) = ([1.0; 4], 0.0, 0.6, false);
        }
        let flags = if vcol.is_some() { FLAG_VCOL } else { 0 } | if clear { FLAG_CLEAR } else { 0 };
        s.gpu_parts.push(GpuPart { idx_off, vtx_off, flags, pad: 0, color, mr: [metal, rough, 0.0, 0.0] });
        s.parts.push(Part { name: node["name"].as_str().unwrap_or("").to_string(), idx_off, idx_count: (ia.count / 3 * 3) as u32, vtx_off, vtx_count: pa.count as u32, clear });
    }
    Ok(s)
}
