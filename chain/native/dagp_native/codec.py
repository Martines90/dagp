"""Canonical, bounded object graph for consensus state. Never decode transaction args.

Only explicitly imported protocol model classes are accepted. No pickle, dynamic
imports, eval, user constructors or host object serialization.
"""
import base64
import importlib
import json
from enum import Enum

MODULES = ('election','params','roles','assignments','parties','campaign','comprehension','session',
           'scale','tally','treasury','proposal','review','payments','emergency',
           'policy','societies','mergers','admin')
MAX_NODES = 50000
MAX_BYTES = 8*1024*1024


def classes():
    result = {}
    for name in MODULES:
        module = importlib.import_module('dagp_ref.'+name)
        for value in vars(module).values():
            if isinstance(value,type) and value.__module__ == module.__name__:
                result[value.__module__+'.'+value.__name__] = value
    from dagp_ref.crypto_sim import MerkleTree
    result[MerkleTree.__module__+"."+MerkleTree.__name__]=MerkleTree
    from .merger import Covenant
    result[Covenant.__module__+"."+Covenant.__name__]=Covenant
    from .engine import World, Receipts
    for value in (World,Receipts):
        result[value.__module__+'.'+value.__name__] = value
    return result


def scalar(value):
    if isinstance(value,Enum):
        return {'enum':value.__class__.__module__+'.'+value.__class__.__name__,'value':value.value}
    if value is None or type(value) in (str,bool,int):
        if type(value) is int and not -(1<<63) <= value < (1<<63):
            raise ValueError('state integer bound')
        return value
    if type(value) is bytes:
        return {'bytes':base64.b64encode(value).decode()}
    if type(value) is tuple:
        return {'tuple':[scalar(v) for v in value]}
    raise ValueError('unsupported graph key or set element')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)


def encode(root):
    nodes,seen=[],{}
    known=classes()
    def item(value):
        if value is None or type(value) in (str,bool,int,bytes) or isinstance(value,Enum):
            return scalar(value)
        ident=id(value)
        if ident in seen:return {'ref':seen[ident]}
        if len(nodes)>=MAX_NODES:raise ValueError('graph node bound')
        index=len(nodes);seen[ident]=index;nodes.append(None)
        if type(value) in (list,tuple):
            node={'kind':type(value).__name__,'items':[item(v) for v in value]}
        elif type(value) in (set,frozenset):
            ordered=sorted(value,key=lambda v:canonical(scalar(v)))
            node={'kind':type(value).__name__,'items':[item(v) for v in ordered]}
        elif type(value) is dict:
            ordered=sorted(value,key=lambda k:canonical(scalar(k)))
            node={'kind':'dict','items':[[item(k),item(value[k])] for k in ordered]}
        else:
            tag=value.__class__.__module__+'.'+value.__class__.__name__
            if tag not in known or not hasattr(value,'__dict__'):raise ValueError('unapproved state class: '+tag)
            node={'kind':'object','class':tag,'attrs':{k:item(v) for k,v in sorted(vars(value).items())}}
        nodes[index]=node
        return {'ref':index}
    graph={'format':1,'root':item(root),'nodes':nodes}
    if len(canonical(graph))>MAX_BYTES:raise ValueError('graph byte bound')
    return graph


def decode(graph):
    if type(graph) is not dict or set(graph)!= {'format','root','nodes'} or graph['format']!=1:
        raise ValueError('graph format')
    nodes=graph['nodes'];known=classes()
    if type(nodes) is not list or len(nodes)>MAX_NODES or len(canonical(graph))>MAX_BYTES:
        raise ValueError('graph bounds')
    memo,building={},set()
    def value(v):
        if v is None or type(v) in (str,bool,int):return scalar(v)
        if type(v) is not dict:raise ValueError('graph value')
        if set(v)=={'bytes'}:return base64.b64decode(v['bytes'],validate=True)
        if set(v)=={'enum','value'}:
            cls=known.get(v['enum'])
            if cls is None or not issubclass(cls,Enum):raise ValueError('unapproved enum')
            return cls(v['value'])
        if set(v)=={'tuple'}:return tuple(value(x) for x in v['tuple'])
        if set(v)!={'ref'}:raise ValueError('unknown graph tag')
        index=v['ref']
        if type(index) is not int or not 0<=index<len(nodes):raise ValueError('graph reference')
        if index in memo:return memo[index]
        if index in building:raise ValueError('immutable graph cycle')
        node=nodes[index];kind=node['kind'];building.add(index)
        if kind=='object':
            cls=known.get(node['class'])
            if cls is None or issubclass(cls,Enum):raise ValueError('unapproved graph class')
            obj=cls.__new__(cls);memo[index]=obj
            for k,vv in node['attrs'].items():object.__setattr__(obj,k,value(vv))
        elif kind=='dict':
            obj={};memo[index]=obj
            for k,vv in node['items']:
                key=value(k)
                if key in obj:raise ValueError('duplicate graph key')
                obj[key]=value(vv)
        elif kind=='list':
            obj=[];memo[index]=obj;obj.extend(value(x) for x in node['items'])
        elif kind in ('tuple','set','frozenset'):
            items=[value(x) for x in node['items']]
            obj={'tuple':tuple,'set':set,'frozenset':frozenset}[kind](items);memo[index]=obj
        else:raise ValueError('unknown graph node')
        building.remove(index);return obj
    result=value(graph['root'])
    if len(memo)!=len(nodes):raise ValueError('unreachable graph nodes')
    return result
