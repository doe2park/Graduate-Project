export function readGLB(buffer){
 if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<20)throw Error('Invalid GLB header');
 const v=new DataView(buffer);if(v.getUint32(0,true)!==0x46546c67||v.getUint32(4,true)!==2)throw Error('A GLB version 2 file is required');
 if(v.getUint32(8,true)!==buffer.byteLength)throw Error('GLB length is invalid');
 let json=null,offset=12;
 while(offset<buffer.byteLength){if(offset+8>buffer.byteLength)throw Error('GLB chunk length is invalid');const n=v.getUint32(offset,true),type=v.getUint32(offset+4,true);if(n%4||offset+8+n>buffer.byteLength)throw Error('GLB chunk length is invalid');if(offset===12&&type!==0x4e4f534a)throw Error('GLB must start with JSON');if(type===0x4e4f534a){if(json)throw Error('Duplicate GLB JSON');json=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,offset+8,n)).trim());}offset+=8+n;}
 if(!json)throw Error('Missing GLB JSON');return json;
}
export function validatePackage(g,m){
 if(m?.schemaVersion!==1)throw Error('Metadata schemaVersion must be 1');
 if(typeof m.buildingId!=='string'||!m.buildingId.trim())throw Error('Declare a buildingId namespace');
 if(typeof m.layer!=='string'||!m.layer.trim())throw Error('Declare a layer');
 if(m.units!=='m'||m.upAxis!=='Y')throw Error('This workshop requires declared units m and upAxis Y');
 if(!m.elements||Array.isArray(m.elements)||typeof m.elements!=='object')throw Error('Missing element identity dictionary');
 for(const [id,record] of Object.entries(m.elements))if(!id||!record||Array.isArray(record)||typeof record!=='object')throw Error(`Invalid element record: ${id}`);
 for(const r of [...(g.images||[]),...(g.buffers||[])])if(r.uri)throw Error('Use embedded GLB resources only; external resources are unsupported');
 const nodes=g.nodes||[],parents=new Array(nodes.length).fill(-1);
 nodes.forEach((n,i)=>{for(const c of n.children||[]){if(!Number.isInteger(c)||c<0||c>=nodes.length||parents[c]!==-1)throw Error('Invalid node hierarchy');parents[c]=i;}});
 for(let i=0;i<nodes.length;i++){const seen=new Set();let j=i;while(j!==-1){if(seen.has(j))throw Error('Cyclic node hierarchy');seen.add(j);j=parents[j];}}
 const ids=new Set(),missing=[];let geometries=0;
 nodes.forEach((n,i)=>{if(n.mesh===undefined)return;if(!g.meshes?.[n.mesh])throw Error('Invalid mesh reference');geometries++;let j=i,id;while(j!==-1){if(Object.hasOwn(m.elements,String(nodes[j].name))){id=String(nodes[j].name);break;}j=parents[j];}if(id===undefined)missing.push(i);else ids.add(id);});
 if(missing.length)throw Error(`Element identity missing for ${missing.length} geometry nodes; preserve source node names and use the matching JSON`);
 if(!geometries)throw Error('No mesh geometry found');
 return {buildingId:m.buildingId,layer:m.layer,matched:ids.size,geometries,metadataRecords:Object.keys(m.elements).length,unusedMetadata:Object.keys(m.elements).filter(id=>!ids.has(id)).length,units:m.units,upAxis:m.upAxis,ids:[...ids],spatiallyRegistered:false};
}
