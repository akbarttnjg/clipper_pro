"""Literal Unicode phrase spans on effective transcript rows; no ASR calls."""
def phrase_groups(words,query,field='word',replacement=None):
    query=query.strip().casefold()
    if not query:return []
    parts=[str(w.get(field,'')) for w in words]
    starts=[];cursor=0
    for part in parts:starts.append(cursor);cursor+=len(part)+1
    text=' '.join(parts);fold=[];positions=[]
    for i,char in enumerate(text):
        folded=char.casefold();fold.append(folded);positions.extend([i]*len(folded))
    folded=''.join(fold);hits=[];offset=0
    while True:
        at=folded.find(query,offset)
        if at<0:break
        left,right=positions[at],positions[at+len(query)-1]+1
        first=next((i for i,start in enumerate(starts) if start<=left<start+len(parts[i])),None)
        last=next((i for i,start in enumerate(starts) if start<right<=start+len(parts[i])),None)
        if first is not None and last is not None and (not hits or left>=hits[-1]['right']):
            hits.append({'first':first,'last':last,'left':left,'right':right})
        offset=at+len(query)
    groups=[]
    for hit in hits:
        if groups and hit['first']<=groups[-1]['last']:
            groups[-1]['last']=max(groups[-1]['last'],hit['last']);groups[-1]['hits'].append(hit)
        else:groups.append({'first':hit['first'],'last':hit['last'],'hits':[hit]})
    for group in groups:
        a=starts[group['first']];b=starts[group['last']]+len(parts[group['last']])
        group['before']=text[a:b];group['origin_word_ids']=list(dict.fromkeys(i for word in words[group['first']:group['last']+1]
            for i in word.get('source_word_ids',word.get('origin_word_ids',[word['word_id']]))))
        if replacement is not None:
            result=[];at=a
            for hit in group['hits']:
                result.extend([text[at:hit['left']],replacement]);at=hit['right']
            group['after']=''.join([*result,text[at:b]])
    return groups
